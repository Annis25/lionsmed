"""Audit transversal permissions/IDOR (Phase C, §11).

Complète — ne remplace pas — les tests ciblés de chaque app. Deux angles :
1. Toute page privée est inaccessible sans authentification (redirection login).
2. Changer un UUID/slug dans l'URL ne donne jamais accès à l'objet d'un autre compte.
"""
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from apps.core.tests.test_foundations import account
from apps.governance.models import Role
from apps.members.models import AssociationExperience
from apps.agenda.models import Event, Registration
from apps.editorial.publication import publish_content
from apps.communications.services import notify
from apps.dues import services as dues_services
from apps.documents import services as documents_services
from apps.documents.models import Document
from apps.documents.scanning import ScanResult
from apps.governance.models import LionsYear
from apps.voting import services as voting_services
from apps.voting.models import Vote


PRIVATE_URLS = [
    "core:dashboard", "members:profile", "members:profile_edit", "members:experiences",
    "members:directory", "governance:dashboard", "governance:members", "governance:years",
    "governance:statistics", "agenda_private:calendar", "agenda_private:attendance_events",
    "documents:list", "documents:manage_list", "notifications:list", "dues:own", "dues:manage_list",
    "voting:member_list", "voting:manage_list", "satisfaction:respond", "satisfaction:manage_list",
    "editorial_management:dashboard",
]


class AnonymousAlwaysRedirectedTests(TestCase):
    def test_every_private_url_redirects_anonymous_to_login(self):
        for name in PRIVATE_URLS:
            with self.subTest(route=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 302)
                self.assertIn("/connexion/", response.url)

    def test_query_string_role_never_grants_access(self):
        response = self.client.get(reverse("governance:dashboard") + "?role=SUPER_ADMIN")
        self.assertEqual(response.status_code, 302)


class CrossAccountObjectAccessTests(TestCase):
    """Deux comptes, deux profils : l'un ne doit jamais lire/modifier l'objet de l'autre."""

    def setUp(self):
        self.owner = account("owner@example.invalid", role=Role.MEMBRE)
        self.other = account("intruder@example.invalid", role=Role.MEMBRE)
        self.president = account("president@example.invalid", role=Role.PRESIDENT)

    def test_experience_of_another_member_not_editable(self):
        experience = AssociationExperience.objects.create(profile=self.owner.member_profile, network="LIONS",
            club="Club", function="Fonction", starts_on=timezone.localdate().replace(day=1))
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("members:experience_edit", args=[experience.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("members:experience_delete", args=[experience.pk])).status_code, 404)

    def test_member_detail_of_hidden_profile_not_exposed(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("members:detail", args=[self.owner.pk])).status_code, 404)

    def test_photo_of_another_member_requires_sharing(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("members:photo", args=[self.owner.pk])).status_code, 404)

    @patch("apps.documents.services.scan_bytes", return_value=ScanResult(clean=True))
    def test_document_grant_is_nominative_not_transferable(self, _scan):
        from django.core.files.uploadedfile import SimpleUploadedFile
        upload = SimpleUploadedFile("doc.pdf", b"%PDF-1.4 x", content_type="application/pdf")
        document = documents_services.upload_document(actor=self.president, upload=upload, title="t", description="",
            category=Document.Category.GENERAL, visibility=Document.Visibility.RESPONSABLES)
        documents_services.grant_access(actor=self.president, document=document, user=self.owner)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("documents:detail", args=[document.pk])).status_code, 200)
        self.client.force_login(self.other)  # même rôle, aucun grant : refusé
        self.assertEqual(self.client.get(reverse("documents:detail", args=[document.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("documents:download", args=[document.pk])).status_code, 404)

    def test_notification_not_readable_or_markable_by_other_account(self):
        notification = notify(recipient=self.owner, category="IMPORTANT", title="t", event_key="idor-audit-1")
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse("notifications:list")), "idor-audit-1")
        self.assertEqual(self.client.post(reverse("notifications:mark_read", args=[notification.pk])).status_code, 404)

    def test_dues_record_of_another_member_not_visible_in_own_list_or_manageable(self):
        year = LionsYear.objects.create(starts_on=timezone.localdate().replace(month=7, day=1),
            ends_on=timezone.localdate().replace(year=timezone.localdate().year + 1, month=7, day=1))
        record = dues_services.ensure_record(actor=self.president, profile=self.owner.member_profile, lions_year=year)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("dues:manage_detail", args=[record.pk])).status_code, 403)
        response = self.client.get(reverse("dues:own"))
        self.assertNotIn(record.pk, {r.pk for r in response.context["records"]})

    def test_event_registration_isolated_per_profile(self):
        event = Event(title="t", slug="idor-audit-event", summary="s", body="b", created_by=self.president,
            updated_by=self.president, starts_at=timezone.now() + timedelta(days=1),
            ends_at=timezone.now() + timedelta(hours=2, days=1), location="loc", visibility="PRIVATE", registration_enabled=True)
        event.save()
        event = publish_content(actor=self.president, obj=event, kind="event")
        from apps.agenda.services import set_registration
        set_registration(actor=self.owner, event=event, status=Registration.Status.CONFIRMED)
        self.client.force_login(self.other)
        self.client.post(reverse("agenda_private:rsvp", args=[event.pk]), {"action": "confirm"})
        owner_reg = Registration.objects.get(event=event, profile=self.owner.member_profile)
        other_reg = Registration.objects.get(event=event, profile=self.other.member_profile)
        self.assertNotEqual(owner_reg.pk, other_reg.pk)
        self.assertEqual(owner_reg.status, Registration.Status.CONFIRMED)

    def test_non_elector_cannot_reach_vote_ballot_by_guessing_id(self):
        vote = Vote(title="t", description="", mode=Vote.Mode.SINGLE, opens_at=timezone.now() - timedelta(minutes=1),
            closes_at=timezone.now() + timedelta(days=1), min_choices=1, max_choices=1, blank_allowed=False, responsible=self.president)
        vote.full_clean()
        vote.save()
        voting_services.add_option(actor=self.president, vote=vote, label="A")
        voting_services.open_vote(actor=self.president, vote=vote)  # figé avant la création de self.other si créé après ; ici self.other existe déjà en setUp
        outsider = account("outsider@example.invalid", role=Role.MEMBRE)  # créé après ouverture : jamais électeur
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(reverse("voting:member_detail", args=[vote.pk])).status_code, 404)
