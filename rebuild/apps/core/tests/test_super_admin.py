"""Super administrateur : rôle le plus étendu, jamais exposé sur le site public.
Décisions du propriétaire (sept. 2026) : boîtes Candidatures/Contact en lecture seule,
réponses de satisfaction nominatives visibles par lui seul, vote secret inchangé."""
from django.test import TestCase, override_settings
from django.urls import reverse
from apps.communications.forms import ContactForm
from apps.communications.services import submit
from apps.core.permissions import CAPABILITIES, can
from apps.core.tests.test_foundations import account
from apps.editorial.tests.test_public import submission
from apps.governance.models import Role
from apps.governance.selectors import mandate_candidates
from apps.members.models import MemberProfile
from apps.satisfaction.services import submit_satisfaction
from apps.satisfaction.tests.test_satisfaction import open_period


class SuperAdminTests(TestCase):
    def setUp(self):
        self.admin = account("admin@example.invalid", role=Role.SUPER_ADMIN)
        self.president = account("president@example.invalid", role=Role.PRESIDENT)
        self.member = account("membre@example.invalid", role=Role.MEMBRE)

    def test_every_capability_except_processing_requests_and_email_change(self):
        missing = {name for name in CAPABILITIES if not can(self.admin, name)}
        self.assertEqual(missing, {"application.manage", "contact.manage", "account.change_email"})

    def test_inboxes_are_read_only(self):
        request = submit(ContactForm(submission("contact")))
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("communications:inbox", args=["contact"])).status_code, 200)
        self.assertEqual(self.client.get(reverse("communications:inbox", args=["application"])).status_code, 200)
        url = reverse("communications:request", kwargs={"kind": "contact", "object_id": request.pk})
        page = self.client.get(url)
        self.assertContains(page, "Consultation seule")
        self.assertNotContains(page, 'name="state"')
        self.assertEqual(self.client.post(url, {"state": "CLOSED"}).status_code, 403)
        request.refresh_from_db()
        self.assertEqual(request.state, "RECEIVED")
        # Consulter n'est pas traiter : aucune carte « À faire » pour ces messages.
        self.assertNotContains(self.client.get(reverse("core:dashboard")), reverse("communications:inbox", args=["contact"]) + '">Consulter')

    def test_individual_satisfaction_responses_are_super_admin_only(self):
        period = open_period(self.president, threshold=5)
        submit_satisfaction(actor=self.member, period=period, score=2, comment="Commentaire nominatif")
        url = reverse("satisfaction:individual", args=[period.pk])
        self.client.force_login(self.president)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertNotContains(self.client.get(reverse("satisfaction:results", args=[period.pk])), "Commentaire nominatif")
        self.client.force_login(self.admin)
        page = self.client.get(url)
        self.assertContains(page, "Compte Synthétique")
        self.assertContains(page, "Commentaire nominatif")
        self.assertContains(self.client.get(reverse("satisfaction:results", args=[period.pk])), url)

    def test_members_are_told_before_answering(self):
        open_period(self.president)
        self.client.force_login(self.member)
        self.assertContains(self.client.get(reverse("satisfaction:respond")), "peut, lui, voir les réponses de chaque personne")

    @override_settings(PUBLIC_INDEXING_ENABLED=True)
    def test_never_exposed_on_the_public_site(self):
        MemberProfile.objects.filter(user=self.admin).update(public_profile_enabled=True, public_slug="admin-technique")
        self.assertEqual(self.client.get("/membres/admin-technique/").status_code, 404)
        self.assertEqual(self.client.get("/membres/admin-technique/photo/").status_code, 404)
        self.assertNotContains(self.client.get("/sitemap.xml"), "admin-technique")
        self.assertNotIn(self.admin.pk, set(mandate_candidates().values_list("user_id", flat=True)))
        self.client.force_login(self.member)
        self.assertNotContains(self.client.get(reverse("members:directory")), "admin@example.invalid")
