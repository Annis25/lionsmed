"""Scrutin nominatif (décision du propriétaire, sept. 2026) : choisi à la création, annoncé aux
électeurs, consultable par le seul Super administrateur après clôture. Un scrutin secret ne
produit jamais de donnée nominative."""
from uuid import uuid4
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from apps.communications.models import Notification
from apps.core.permissions import CAPABILITIES
from apps.core.tests.test_foundations import account
from apps.governance.models import Role
from .. import services
from ..models import Ballot, NominativeChoice, Vote
from .test_voting import opened_vote


class NominativeVoteTests(TestCase):
    def setUp(self):
        self.admin = account("admin@example.invalid", role=Role.SUPER_ADMIN)
        self.president = account("president@example.invalid", role=Role.PRESIDENT)
        self.member = account("membre@example.invalid", role=Role.MEMBRE)
        self.member.first_name, self.member.last_name = "Sami", "Trabelsi"
        self.member.save()
        self.other = account("autre@example.invalid", role=Role.MEMBRE)

    def cast(self, actor, vote, label=None, blank=False):
        ids = [] if blank else [vote.options.get(label=label).pk]
        return services.cast_vote(actor=actor, vote=vote, option_ids=ids, is_blank=blank)

    def test_only_super_admin_holds_the_capability(self):
        self.assertEqual(CAPABILITIES["vote.view_nominative"], frozenset({Role.SUPER_ADMIN}))

    def test_secret_vote_never_records_who_chose_what(self):
        vote = opened_vote(self.president)
        self.assertEqual(vote.disclosure, Vote.Disclosure.SECRET)  # défaut, y compris pour l'existant
        self.cast(self.member, vote, "Proposition A")
        self.assertEqual(Ballot.objects.filter(vote=vote).count(), 1)
        self.assertFalse(NominativeChoice.objects.exists())
        services.close_vote(actor=self.president, vote=vote)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("voting:nominative", args=[vote.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("voting:results", args=[vote.pk])), "choix nominatifs")

    def test_nominative_vote_records_choice_beside_the_anonymous_ballot(self):
        vote = opened_vote(self.president, disclosure=Vote.Disclosure.NOMINATIVE, blank_allowed=True)
        ballot = self.cast(self.member, vote, "Proposition B")
        self.cast(self.other, vote, blank=True)
        record = NominativeChoice.objects.get(elector__profile__user=self.member)
        self.assertEqual([o.label for o in record.options.all()], ["Proposition B"])
        self.assertTrue(NominativeChoice.objects.get(elector__profile__user=self.other).is_blank)
        # Le bulletin reste anonyme : aucun champ vers l'électeur, aucun lien depuis la trace nominative.
        self.assertFalse(any(f.name in {"profile", "user", "elector", "nominative_choice"} for f in Ballot._meta.get_fields()))
        self.assertFalse(any(getattr(f, "related_model", None) is Ballot for f in NominativeChoice._meta.get_fields()))
        self.assertEqual(ballot.selections.get().option.label, "Proposition B")

    def test_only_super_admin_sees_choices_and_only_after_closure(self):
        vote = opened_vote(self.president, disclosure=Vote.Disclosure.NOMINATIVE)
        self.cast(self.member, vote, "Proposition A")
        url = reverse("voting:nominative", args=[vote.pk])
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 403)  # scrutin encore ouvert
        services.close_vote(actor=self.president, vote=vote)
        for user in (self.president, self.member):
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertNotContains(self.client.get(reverse("voting:results", args=[vote.pk])), url)
        self.client.force_login(self.admin)
        page = self.client.get(url)
        self.assertContains(page, "Sami Trabelsi")
        self.assertContains(page, "Proposition A")
        self.assertContains(page, "N’a pas voté")
        self.assertContains(self.client.get(reverse("voting:results", args=[vote.pk])), url)
        self.assertContains(self.client.get(reverse("voting:manage_track", args=[vote.pk])), url)

    def test_electors_are_warned_before_voting(self):
        vote = opened_vote(self.president, disclosure=Vote.Disclosure.NOMINATIVE)
        self.client.force_login(self.member)
        self.assertContains(self.client.get(reverse("voting:member_detail", args=[vote.pk])), "Vote nominatif.")
        self.assertContains(self.client.get(reverse("voting:member_list")), "Vote nominatif")
        recap = self.client.post(reverse("voting:member_detail", args=[vote.pk]),
            {"ballot_choice": str(vote.options.get(label="Proposition A").pk)})
        self.assertContains(recap, "votre choix sera visible par l’administrateur du site")
        self.assertNotContains(recap, "Votre vote est anonyme")
        secret = opened_vote(self.president)
        self.assertContains(self.client.get(reverse("voting:member_detail", args=[secret.pk])), "Votre vote est anonyme et définitif.")

    def test_creation_form_fixes_disclosure_and_notifies_electors(self):
        self.client.force_login(self.president)
        self.client.post(reverse("voting:manage_create"), {"creation_key": str(uuid4()), "title": "Élection du bureau",
            "description": "", "mode": "SINGLE", "disclosure": "NOMINATIVE", "options": ["Oui", "Non"]})
        vote = Vote.objects.get(title="Élection du bureau")
        self.assertEqual((vote.status, vote.disclosure), (Vote.Status.OPEN, Vote.Disclosure.NOMINATIVE))
        notice = Notification.objects.get(recipient=self.member, event_key__startswith="vote_opened:")
        self.assertIn("nominatif", notice.excerpt)
        from apps.communications.outbox import deliver_batch
        from django.test import override_settings
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            deliver_batch()
        bodies = [message.body for message in mail.outbox if "membre@example.invalid" in message.to]
        self.assertTrue(bodies and "vote nominatif" in bodies[0])
