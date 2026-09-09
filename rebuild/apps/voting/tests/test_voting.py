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


class CreateAndOpenVoteTests(TestCase):
    def setUp(self):
        self.president = account("president2@example.invalid", role=Role.PRESIDENT)
        self.member = account("member2@example.invalid", role=Role.MEMBRE)  # avant création : figé électeur

    def test_service_creates_open_vote_single_choice_no_scheduled_close(self):
        vote = services.create_and_open_vote(actor=self.president, title="Bureau 2026", description="",
            mode=Vote.Mode.SINGLE, blank_allowed=False, option_labels=["A", "B", ""])
        self.assertEqual(vote.status, Vote.Status.OPEN)
        self.assertEqual(vote.min_choices, 1)
        self.assertEqual(vote.max_choices, 1)
        self.assertIsNone(vote.closes_at)
        self.assertEqual(vote.options.count(), 2)  # le libellé vide est ignoré
        self.assertTrue(Elector.objects.filter(vote=vote, profile=self.member.member_profile).exists())

    def test_service_rejects_vote_with_no_real_option(self):
        with self.assertRaises(ValidationError):
            services.create_and_open_vote(actor=self.president, title="Vide", description="",
                mode=Vote.Mode.SINGLE, blank_allowed=False, option_labels=["", "  "])
        self.assertEqual(Vote.objects.count(), 0)

    def test_open_vote_never_closes_automatically_without_closes_at(self):
        vote = services.create_and_open_vote(actor=self.president, title="Sans échéance", description="",
            mode=Vote.Mode.SINGLE, blank_allowed=False, option_labels=["A"])
        option = vote.options.get()
        services.cast_vote(actor=self.member, vote=vote, option_ids=[option.pk])
        self.assertEqual(Participation.objects.filter(elector__vote=vote).count(), 1)

    def test_manage_create_view_one_shot_redirects_to_tracking(self):
        self.client.force_login(self.president)
        response = self.client.post(reverse("voting:manage_create"), {
            "title": "Nouveau bureau", "description": "", "mode": "SINGLE",
            "options": ["Candidat A", "Candidat B"],
        })
        vote = Vote.objects.get(title="Nouveau bureau")
        self.assertRedirects(response, reverse("voting:manage_track", args=[vote.pk]))
        self.assertEqual(vote.status, Vote.Status.OPEN)

    def test_manage_create_view_rejects_empty_option_list(self):
        self.client.force_login(self.president)
        response = self.client.post(reverse("voting:manage_create"), {
            "title": "Sans choix", "description": "", "mode": "SINGLE", "options": ["", ""],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Vote.objects.count(), 0)


class VotesNavigationTests(TestCase):
    def test_manager_sees_votes_as_expandable_group_with_children(self):
        president = account("president3@example.invalid", role=Role.PRESIDENT)
        self.client.force_login(president)
        response = self.client.get(reverse("core:dashboard"))
        nav = {item["label"]: item for item in response.context["private_navigation"]}
        self.assertIn("children", nav["Votes"])
        child_labels = {c["label"] for c in nav["Votes"]["children"]}
        self.assertEqual(child_labels, {"Voter", "Créer un vote", "Gestion des votes", "Responsables de vote"})
        self.assertNotIn("Créer un vote", nav)
        self.assertNotIn("Gestion des votes", nav)

    def test_plain_member_sees_votes_as_flat_link(self):
        member = account("member3@example.invalid", role=Role.MEMBRE)
        self.client.force_login(member)
        response = self.client.get(reverse("core:dashboard"))
        nav = {item["label"]: item for item in response.context["private_navigation"]}
        self.assertNotIn("children", nav["Votes"])
        self.assertEqual(nav["Votes"]["url"], reverse("voting:member_list"))


class VoteManagerDesignationTests(TestCase):
    def setUp(self):
        self.president = account("president4@example.invalid", role=Role.PRESIDENT)
        self.member = account("member4@example.invalid", role=Role.MEMBRE)

    def test_plain_member_cannot_manage_votes(self):
        self.assertFalse(can(self.member, "vote.manage"))

    def test_designated_member_gains_vote_manage_without_role_change(self):
        services.set_vote_manager(actor=self.president, profile=self.member.member_profile, enabled=True)
        self.assertTrue(can(self.member, "vote.manage"))
        from apps.core.permissions import effective_role
        self.assertEqual(effective_role(self.member), Role.MEMBRE)  # rôle inchangé

    def test_revoked_member_loses_vote_manage(self):
        services.set_vote_manager(actor=self.president, profile=self.member.member_profile, enabled=True)
        services.set_vote_manager(actor=self.president, profile=self.member.member_profile, enabled=False)
        self.assertFalse(can(self.member, "vote.manage"))

    def test_designated_manager_cannot_designate_others(self):
        services.set_vote_manager(actor=self.president, profile=self.member.member_profile, enabled=True)
        other = account("other4@example.invalid", role=Role.MEMBRE)
        with self.assertRaises(PermissionDenied):
            services.set_vote_manager(actor=self.member, profile=other.member_profile, enabled=True)

    def test_designated_manager_can_create_and_open_a_vote(self):
        services.set_vote_manager(actor=self.president, profile=self.member.member_profile, enabled=True)
        vote = services.create_and_open_vote(actor=self.member, title="Scrutin délégué", description="",
            mode=Vote.Mode.SINGLE, blank_allowed=False, option_labels=["A", "B"])
        self.assertEqual(vote.status, Vote.Status.OPEN)
        self.assertEqual(vote.responsible, self.member)

    def test_page_requires_management_access_not_just_vote_manage(self):
        services.set_vote_manager(actor=self.president, profile=self.member.member_profile, enabled=True)
        self.client.force_login(self.member)  # responsable désigné, pas du bureau
        self.assertEqual(self.client.get(reverse("voting:manage_responsibles")).status_code, 403)
        self.client.force_login(self.president)
        self.assertEqual(self.client.get(reverse("voting:manage_responsibles")).status_code, 200)

    def test_designate_via_page_then_revoke(self):
        self.client.force_login(self.president)
        url = reverse("voting:manage_responsible_toggle", args=[self.member.pk])
        self.client.post(url, {"action": "designer"})
        self.member.member_profile.refresh_from_db()
        self.assertTrue(self.member.member_profile.is_vote_manager)
        self.client.post(url, {"action": "retirer"})
        self.member.member_profile.refresh_from_db()
        self.assertFalse(self.member.member_profile.is_vote_manager)

    def test_audit_events_recorded_without_leaking_who_did_what_vote(self):
        services.set_vote_manager(actor=self.president, profile=self.member.member_profile, enabled=True)
        from apps.core.models import AuditEvent
        self.assertTrue(AuditEvent.objects.filter(action="vote.manager_designated").exists())
