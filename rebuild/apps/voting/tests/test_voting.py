from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connections, IntegrityError
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from apps.core.tests.test_foundations import account
from apps.core.permissions import can
from apps.governance.models import Role
from .. import services
from ..models import Vote, VoteOption, Elector, Participation, Ballot, BallotSelection


def draft_vote(actor, **kwargs):
    data = dict(title="Scrutin synthétique", description="", mode=Vote.Mode.SINGLE,
        opens_at=timezone.now() - timedelta(minutes=1), closes_at=timezone.now() + timedelta(days=1),
        min_choices=1, max_choices=1, blank_allowed=False, responsible=actor)
    data.update(kwargs)
    vote = Vote(**data)
    vote.full_clean()
    vote.save()
    return vote


def opened_vote(actor, **kwargs):
    vote = draft_vote(actor, **kwargs)
    services.add_option(actor=actor, vote=vote, label="Proposition A")
    services.add_option(actor=actor, vote=vote, label="Proposition B")
    return services.open_vote(actor=actor, vote=vote)


class VoteLifecycleTests(TestCase):
    def setUp(self):
        self.president = account("president@example.invalid", role=Role.PRESIDENT)
        self.bureau = account("bureau@example.invalid", role=Role.BUREAU)
        self.directeur = account("directeur@example.invalid", role=Role.DIRECTEUR)
        self.secretaire = account("secretaire@example.invalid", role=Role.SECRETAIRE)
        self.member = account("member@example.invalid", role=Role.MEMBRE)
        self.invite = account("guest@example.invalid", role=Role.INVITE)
        self.other_member = account("other@example.invalid", role=Role.MEMBRE)

    def test_bureau_cannot_manage_votes(self):
        vote = draft_vote(self.president)
        with self.assertRaises(PermissionDenied):
            services.add_option(actor=self.bureau, vote=vote, label="x")
        with self.assertRaises(PermissionDenied):
            services.open_vote(actor=self.bureau, vote=vote)

    def test_directeur_cannot_manage_votes(self):
        vote = draft_vote(self.president)
        with self.assertRaises(PermissionDenied):
            services.open_vote(actor=self.directeur, vote=vote)

    def test_secretaire_can_manage_votes(self):
        vote = draft_vote(self.secretaire)
        services.add_option(actor=self.secretaire, vote=vote, label="A")
        opened = services.open_vote(actor=self.secretaire, vote=vote)
        self.assertEqual(opened.status, Vote.Status.OPEN)

    def test_opening_freezes_electors_excludes_invite(self):
        vote = opened_vote(self.president)
        elector_ids = set(Elector.objects.filter(vote=vote).values_list("profile__user_id", flat=True))
        self.assertIn(self.member.pk, elector_ids)
        self.assertNotIn(self.invite.pk, elector_ids)

    def test_invite_refused_at_cast(self):
        vote = opened_vote(self.president)
        option = vote.options.first()
        with self.assertRaises(PermissionDenied):
            services.cast_vote(actor=self.invite, vote=vote, option_ids=[option.pk])

    def test_non_elector_member_refused(self):
        vote = opened_vote(self.president)
        late_joiner = account("late@example.invalid", role=Role.MEMBRE)  # rejoint après le gel
        option = vote.options.first()
        with self.assertRaises(PermissionDenied):
            services.cast_vote(actor=late_joiner, vote=vote, option_ids=[option.pk])

    def test_elector_can_vote_and_ballot_is_final(self):
        vote = opened_vote(self.president)
        option = vote.options.first()
        services.cast_vote(actor=self.member, vote=vote, option_ids=[option.pk])
        self.assertEqual(Ballot.objects.filter(vote=vote).count(), 1)
        with self.assertRaises(ValidationError):
            services.cast_vote(actor=self.member, vote=vote, option_ids=[option.pk])

    def test_option_from_another_vote_refused(self):
        vote = opened_vote(self.president)
        other_vote = opened_vote(self.secretaire)
        foreign_option = other_vote.options.first()
        with self.assertRaises(ValidationError):
            services.cast_vote(actor=self.member, vote=vote, option_ids=[foreign_option.pk])

    def test_cardinality_enforced(self):
        vote = opened_vote(self.president, mode=Vote.Mode.SINGLE, min_choices=1, max_choices=1)
        options = list(vote.options.all())
        with self.assertRaises(ValidationError):
            services.cast_vote(actor=self.member, vote=vote, option_ids=[o.pk for o in options])

    def test_blank_and_choice_together_refused(self):
        vote = opened_vote(self.president, blank_allowed=True)
        option = vote.options.first()
        with self.assertRaises(ValidationError):
            services.cast_vote(actor=self.member, vote=vote, option_ids=[option.pk], is_blank=True)

    def test_blank_disallowed_by_default(self):
        vote = opened_vote(self.president)
        with self.assertRaises(ValidationError):
            services.cast_vote(actor=self.member, vote=vote, option_ids=[], is_blank=True)

    def test_vote_before_opening_refused(self):
        vote = draft_vote(self.president, opens_at=timezone.now() + timedelta(days=1), closes_at=timezone.now() + timedelta(days=2))
        services.add_option(actor=self.president, vote=vote, label="A")
        with self.assertRaises(ValidationError):
            services.cast_vote(actor=self.member, vote=vote, option_ids=[])

    def test_vote_after_closing_window_refused_even_if_status_stale(self):
        vote = opened_vote(self.president, closes_at=timezone.now() + timedelta(seconds=1))
        import time as time_module
        time_module.sleep(1.2)
        option = vote.options.first()
        with self.assertRaises(ValidationError):
            services.cast_vote(actor=self.member, vote=vote, option_ids=[option.pk])

    def test_results_refused_before_closure(self):
        vote = opened_vote(self.president)
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse("voting:results", args=[vote.pk])).status_code, 403)
        self.client.force_login(self.president)  # même le responsable ne voit rien avant clôture
        self.assertEqual(self.client.get(reverse("voting:results", args=[vote.pk])).status_code, 403)

    def test_results_available_to_electors_after_closure(self):
        vote = opened_vote(self.president)
        option = vote.options.first()
        services.cast_vote(actor=self.member, vote=vote, option_ids=[option.pk])
        services.close_vote(actor=self.president, vote=vote)
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse("voting:results", args=[vote.pk])).status_code, 200)
        self.client.force_login(self.other_member)  # électeur mais n'a pas voté : toujours autorisé après clôture
        self.assertEqual(self.client.get(reverse("voting:results", args=[vote.pk])).status_code, 200)

    def test_results_refused_to_non_elector_after_closure(self):
        vote = opened_vote(self.president)
        services.close_vote(actor=self.president, vote=vote)
        outsider = account("outsider@example.invalid", role=Role.MEMBRE)
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(reverse("voting:results", args=[vote.pk])).status_code, 403)

    def test_close_is_idempotent(self):
        vote = opened_vote(self.president)
        services.close_vote(actor=self.president, vote=vote)
        closed_at = Vote.objects.get(pk=vote.pk).closed_at
        services.close_vote(actor=self.president, vote=vote)
        self.assertEqual(Vote.objects.get(pk=vote.pk).closed_at, closed_at)

    def test_tracking_shows_participation_never_choice(self):
        vote = opened_vote(self.president)
        option = vote.options.first()
        services.cast_vote(actor=self.member, vote=vote, option_ids=[option.pk])
        self.client.force_login(self.president)
        response = self.client.get(reverse("voting:manage_track", args=[vote.pk]))
        self.assertContains(response, "A voté")
        self.assertNotContains(response, option.label)

    def test_bureau_cannot_track_or_close(self):
        vote = opened_vote(self.president)
        with self.assertRaises(PermissionDenied):
            services.close_vote(actor=self.bureau, vote=vote)
        self.client.force_login(self.bureau)
        self.assertEqual(self.client.get(reverse("voting:manage_track", args=[vote.pk])).status_code, 403)

    def test_db_trigger_rejects_cross_vote_selection_bypassing_service(self):
        """Défense en profondeur : même un INSERT ORM direct, hors cast_vote(), est bloqué par le trigger PostgreSQL."""
        vote = opened_vote(self.president)
        other_vote = opened_vote(self.secretaire)
        foreign_option = other_vote.options.first()
        ballot = Ballot.objects.create(vote=vote, is_blank=False)
        with self.assertRaises(Exception):
            BallotSelection.objects.create(ballot=ballot, option=foreign_option)

    def test_participation_has_no_ballot_reference_and_ballot_has_no_member_reference(self):
        self.assertNotIn("ballot", [f.name for f in Participation._meta.get_fields()])
        self.assertFalse(any(f.name in {"profile", "user", "elector"} for f in Ballot._meta.get_fields() if f.concrete))


class VoteConcurrencyTests(TransactionTestCase):
    def test_two_simultaneous_ballots_from_same_elector_only_one_accepted(self):
        president = account("president@example.invalid", role=Role.PRESIDENT)
        member = account("member@example.invalid", role=Role.MEMBRE)  # créé avant l'ouverture pour être figé électeur
        vote = opened_vote(president)
        option = vote.options.first()

        def attempt(_):
            try:
                services.cast_vote(actor=member, vote=vote, option_ids=[option.pk])
                return True
            except (ValidationError, IntegrityError):
                return False
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, range(2)))
        self.assertEqual(sum(results), 1)
        self.assertEqual(Ballot.objects.filter(vote=vote).count(), 1)
        self.assertEqual(Participation.objects.filter(elector__vote=vote).count(), 1)
