"""Parcours HTTP réels, CSRF actif, PostgreSQL isolé et mails locmem uniquement."""
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import AuditEvent
from apps.core.tests.test_foundations import account
from apps.documents.models import Document
from apps.documents.scanning import ScanResult, ScannerUnavailable
from apps.documents.tests.test_documents import pdf
from apps.dues.models import DuesRecord
from apps.dues.tests.test_dues import lions_year
from apps.governance.models import ClubState, Role
from apps.members.models import MembershipApplication
from apps.communications.models import ContactRequest, OutboxMessage
from apps.communications.outbox import deliver_batch
from apps.agenda.models import Event
from apps.satisfaction.models import SatisfactionPeriod, SatisfactionResponse
from apps.voting.models import Vote, Participation, Ballot


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class FunctionalJourneys(TestCase):
    def setUp(self):
        self.president = account("journey-president@example.invalid", role=Role.PRESIDENT)
        self.secretary = account("journey-secretary@example.invalid", role=Role.SECRETAIRE)
        self.member = account("journey-member@example.invalid")
        self.client = Client(enforce_csrf_checks=True)
        storage = TemporaryDirectory(prefix="lionsmed-functional-")
        self.addCleanup(storage.cleanup)
        override = override_settings(PRIVATE_MEDIA_ROOT=Path(storage.name))
        override.enable()
        self.addCleanup(override.disable)

    def post(self, actor, url, data):
        self.client.force_login(actor)
        self.client.get(reverse("communications:contact"))
        token = self.client.cookies[settings.CSRF_COOKIE_NAME].value
        return self.client.post(url, {**data, "csrfmiddlewaretoken": token})

    def survey(self, threshold=1):
        now = timezone.localtime().replace(second=0, microsecond=0)
        data = {"year": now.year, "month": now.month, "threshold": threshold,
            "opens_at": (now-timedelta(hours=1)).isoformat(), "closes_at": (now+timedelta(days=1)).isoformat(),
            "title": "Avis du club", "description": "Consultation synthétique", "axes": "Organisation\nCommunication"}
        response = self.post(self.secretary, reverse("satisfaction:manage_list"), data)
        self.assertEqual(response.status_code, 302)
        return SatisfactionPeriod.objects.get(), data

    def test_satisfaction_create_edit_respond_results_and_replay(self):
        period, data = self.survey()
        edit = reverse("satisfaction:edit", args=[period.pk])
        self.assertEqual(self.post(self.president, edit, {**data, "axes": "Ambiance\nOrganisation"}).status_code, 302)
        axes = list(period.axes.all())
        answer = {"score": "4", "comment": "COMMENTAIRE_CONFIDENTIEL", **{f"axis_{a.pk}": "5" for a in axes}}
        self.assertEqual(self.post(self.member, reverse("satisfaction:respond"), answer).status_code, 302)
        self.post(self.member, reverse("satisfaction:respond"), answer)
        self.assertEqual(SatisfactionResponse.objects.count(), 1)
        self.assertEqual(SatisfactionResponse.objects.get().axis_scores.count(), 2)
        # Un POST forgé ne peut pas modifier les champs figés après réponse.
        self.assertEqual(self.post(self.secretary, edit, {**data, "title": "Titre corrigé", "axes": "AXE_FORGE", "threshold": 0}).status_code, 302)
        period.refresh_from_db()
        self.assertEqual(period.title, "Titre corrigé")
        self.assertEqual(list(period.axes.values_list("label", flat=True)), ["Ambiance", "Organisation"])
        self.assertEqual(period.threshold, 1)
        self.client.force_login(self.president)
        results = self.client.get(reverse("satisfaction:results", args=[period.pk]))
        self.assertContains(results, "<meter")
        self.assertEqual(results.context["results"]["average"], 4)
        self.assertNotContains(results, "COMMENTAIRE_CONFIDENTIEL")
        self.assertNotContains(results, self.member.email)

    def test_satisfaction_missing_axis_and_closed_window_leave_no_response(self):
        period, _ = self.survey()
        response = self.post(self.member, reverse("satisfaction:respond"), {"score": "4"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(SatisfactionResponse.objects.exists())
        SatisfactionPeriod.objects.filter(pk=period.pk).update(closes_at=timezone.now()-timedelta(minutes=1))
        answer = {"score": "4", **{f"axis_{a.pk}": "5" for a in period.axes.all()}}
        self.post(self.member, reverse("satisfaction:respond"), answer)
        self.assertFalse(SatisfactionResponse.objects.exists())
        self.assertFalse(AuditEvent.objects.filter(action="satisfaction.responded").exists())

    def test_satisfaction_results_hidden_below_threshold(self):
        period, _ = self.survey(threshold=2)
        self.post(self.member, reverse("satisfaction:respond"), {"score": "4", **{f"axis_{a.pk}": "5" for a in period.axes.all()}})
        self.client.force_login(self.president)
        response = self.client.get(reverse("satisfaction:results", args=[period.pk]))
        self.assertTrue(response.context["results"]["hidden"])
        self.assertNotContains(response, "<meter")

    def upload(self, visibility="MEMBERS"):
        return self.post(self.president, reverse("documents:upload"), {"title": "Document synthétique", "category": "GENERAL", "visibility": visibility, "file": pdf()})

    def test_document_upload_download_and_named_access_revocation(self):
        guest = account("journey-guest@example.invalid", role=Role.INVITE)
        with patch("apps.documents.services.scan_bytes", return_value=ScanResult(True)):
            self.assertEqual(self.upload("RESPONSABLES").status_code, 302)
        document = Document.objects.get()
        download = reverse("documents:download", args=[document.pk])
        self.client.force_login(guest)
        self.assertEqual(self.client.get(download).status_code, 404)
        manage = reverse("documents:manage_detail", args=[document.pk])
        self.assertEqual(self.post(self.president, manage, {"email": guest.email}).status_code, 302)
        self.client.force_login(guest)
        self.assertEqual(self.client.head(download).status_code, 200)
        response = self.client.get(download)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"%PDF", b"".join(response.streaming_content))
        grant = document.grants.get()
        self.assertEqual(self.post(self.president, reverse("documents:manage_revoke", args=[document.pk, grant.pk]), {}).status_code, 302)
        self.client.force_login(guest)
        for method in (self.client.get, self.client.head):
            self.assertEqual(method(download).status_code, 404)

    def test_document_scanner_failures_refuse_http_upload_without_storage(self):
        from pathlib import Path
        cases = [ScanResult(False), ScannerUnavailable(), TimeoutError(), RuntimeError()]
        for outcome in cases:
            with self.subTest(outcome=type(outcome).__name__):
                arguments = {"side_effect": outcome} if isinstance(outcome, Exception) else {"return_value": outcome}
                with patch("apps.documents.services.scan_bytes", **arguments):
                    response = self.upload()
                self.assertEqual(response.status_code, 200)
                self.assertIn("file", response.context["form"].errors)
                self.assertFalse(Document.objects.exists())
                self.assertFalse([p for p in Path(settings.PRIVATE_MEDIA_ROOT).rglob("*") if p.is_file()])
        self.assertFalse(AuditEvent.objects.filter(action="document.uploaded").exists())

    def vote(self):
        self.client.force_login(self.president)
        url = reverse("voting:manage_create")
        key = self.client.get(url).context["form"].initial["creation_key"]
        data = {"title": "Vote synthétique", "mode": "SINGLE", "options": ["Oui", "Non"], "creation_key": str(key)}
        for _ in range(2):
            self.assertEqual(self.post(self.president, url, data).status_code, 302)
        self.assertEqual(Vote.objects.count(), 1)
        self.assertEqual(AuditEvent.objects.filter(action="vote.created").count(), 1)
        return Vote.objects.get()

    def test_vote_create_confirm_replay_close_and_results(self):
        vote = self.vote()
        option = vote.options.first()
        selection = {"options": [str(option.pk)]}
        preview = self.post(self.member, reverse("voting:member_detail", args=[vote.pk]), selection)
        self.assertEqual(preview.status_code, 200)
        self.assertFalse(Ballot.objects.exists())
        for _ in range(2):
            self.assertEqual(self.post(self.member, reverse("voting:member_confirm", args=[vote.pk]), selection).status_code, 302)
        self.assertEqual(Ballot.objects.count(), 1)
        self.assertEqual(Participation.objects.count(), 1)
        self.assertEqual(self.post(self.president, reverse("voting:manage_close", args=[vote.pk]), {}).status_code, 302)
        vote.refresh_from_db()
        self.assertEqual(vote.status, "CLOSED")
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse("voting:results", args=[vote.pk])).status_code, 200)
        self.assertFalse({"profile", "elector", "user", "ip"} & {f.name for f in Ballot._meta.fields})

    def test_vote_missing_token_and_foreign_choice_create_no_mutation(self):
        self.assertEqual(self.post(self.president, reverse("voting:manage_create"), {"title": "Invalide", "mode": "SINGLE", "options": ["Oui"]}).status_code, 200)
        self.assertFalse(Vote.objects.exists())
        vote = self.vote()
        self.post(self.member, reverse("voting:member_confirm", args=[vote.pk]), {"options": [str(uuid4())]})
        self.assertFalse(Ballot.objects.exists())
        self.assertFalse(Participation.objects.exists())

    def test_profile_phone_valid_and_invalid_preserve_existing_data(self):
        url = reverse("members:profile_edit")
        data = {"first_name": "Compte", "last_name": "Synthétique", "phone": "20 123 456"}
        self.assertEqual(self.post(self.member, url, data).status_code, 302)
        self.member.member_profile.refresh_from_db()
        self.assertEqual(self.member.member_profile.phone, "+21620123456")
        for value in ("abc", "22AA4455", "+216HELLO", "2012", "201234567"):
            response = self.post(self.member, url, {**data, "phone": value})
            self.assertEqual(response.status_code, 200)
            self.assertIn("phone", response.context["form"].errors)
            self.member.member_profile.refresh_from_db()
            self.assertEqual(self.member.member_profile.phone, "+21620123456")

    @override_settings(CONTACT_RECIPIENT="contact-test@example.invalid")
    def test_public_contact_and_application_phone_submission_replay_and_inbox(self):
        for kind, Model, actor in (("contact", ContactRequest, self.secretary), ("application", MembershipApplication, account("journey-gmt@example.invalid", role=Role.GMT))):
            client = Client(enforce_csrf_checks=True)
            url = reverse("communications:"+kind)
            form = client.get(url).context["form"]
            data = {"submission_token": form.initial["submission_token"], "csrfmiddlewaretoken": client.cookies[settings.CSRF_COOKIE_NAME].value,
                "email": kind+"@example.invalid", "phone": "22AA4455", "name": "Contact synthétique", "subject": "AUTRE", "message": "Message synthétique",
                "first_name": "Compte", "last_name": "Synthétique", "motivation": "Participer aux actions", "consent": "on"}
            response = client.post(url, data)
            self.assertEqual(response.status_code, 200)
            self.assertIn("phone", response.context["form"].errors)
            self.assertFalse(Model.objects.exists())
            data["phone"] = "20123456"
            for _ in range(2):
                self.assertEqual(client.post(url, data).status_code, 302)
            self.assertEqual(Model.objects.count(), 1)
            obj = Model.objects.get()
            self.assertEqual(obj.phone, "+21620123456")
            self.assertEqual(OutboxMessage.objects.filter(kind=kind.upper()).count(), 1)
            self.client.force_login(actor)
            self.assertEqual(self.client.get(reverse("communications:request", kwargs={"kind": kind, "object_id": obj.pk})).status_code, 200)

    def test_dues_unpaid_partial_paid_correction_and_year_isolation(self):
        treasurer = account("journey-treasurer@example.invalid", role=Role.TRESORIER)
        year = lions_year()
        ClubState.objects.update_or_create(pk=1, defaults={"active_year": year})
        listing = reverse("dues:manage_list")
        self.client.force_login(treasurer)
        self.assertEqual(self.client.get(listing).context["counts"]["paid"], 0)
        for tranche, expected in ((1, "PARTIAL"), (2, "PAID")):
            url = reverse("dues:manage_set", args=[year.pk, self.member.member_profile.pk, tranche])
            self.assertEqual(self.post(treasurer, url, {"paid": "1", "paid_on": "2026-09-15"}).status_code, 302)
            record = DuesRecord.objects.get(profile=self.member.member_profile, lions_year=year)
            self.assertEqual(record.status, expected)
        self.assertEqual(self.client.get(listing, {"status": "PAID"}).context["page_obj"].paginator.count, 1)
        url = reverse("dues:manage_set", args=[year.pk, self.member.member_profile.pk, 2])
        self.post(treasurer, url, {"paid": "0", "motif": "Correction synthétique"})
        record.refresh_from_db()
        self.assertEqual(record.status, "PARTIAL")
        self.assertIsNone(record.tranche2_paid_on)
        self.assertEqual(record.changes.count(), 3)
        self.assertEqual(self.post(self.president, url, {"paid": "1"}).status_code, 403)
        self.post(treasurer, url, {"paid": "1", "paid_on": "date-invalide"})
        record.refresh_from_db()
        self.assertFalse(record.tranche2_paid)
        self.assertEqual(self.post(treasurer, reverse("dues:manage_set", args=[999999, self.member.member_profile.pk, 1]), {"paid": "1"}).status_code, 404)

    def test_event_creation_replay_delivery_and_revoked_recipient(self):
        self.client.force_login(self.president)
        key = self.client.get(reverse("agenda_private:calendar")).context["quick_form"].initial["creation_key"]
        data = {"creation_key": str(key), "title": "Événement proche", "starts_at": (timezone.now()+timedelta(days=2)).isoformat(), "location": "Club"}
        url = reverse("agenda_private:calendar_event_add")
        for _ in range(2):
            self.assertEqual(self.post(self.president, url, data).status_code, 302)
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(OutboxMessage.objects.filter(kind="EVENT_CREATED").count(), 3)
        self.member.is_active = False
        self.member.save(update_fields=["is_active"])
        result = deliver_batch(limit=10)
        self.assertEqual(result["sent"], 2)
        item = OutboxMessage.objects.get(kind="EVENT_CREATED", recipient=self.member.email)
        self.assertEqual((item.state, item.error_code), ("FAILED", "not_applicable"))
        self.assertEqual(len(mail.outbox), 2)
        self.assertFalse(any(self.member.email in message.to for message in mail.outbox))

    def test_forged_post_permissions_and_missing_csrf_leave_no_mutations(self):
        routes = ["satisfaction:manage_list", "documents:upload", "voting:manage_create", "agenda_private:calendar_event_add"]
        for name in routes:
            self.assertEqual(self.post(self.member, reverse(name), {}).status_code, 403)
        self.client.force_login(self.president)
        for name in routes:
            self.assertEqual(self.client.post(reverse(name), {}).status_code, 403)
        self.assertFalse(SatisfactionPeriod.objects.exists())
        self.assertFalse(Document.objects.exists())
        self.assertFalse(Vote.objects.exists())
        self.assertFalse(Event.objects.exists())
        self.assertFalse(AuditEvent.objects.exists())

    def test_management_get_post_matrix_all_fourteen_roles(self):
        from apps.core.permissions import MANAGERS
        for role in Role.values:
            actor = account(f"journey-role-{role.lower()}@example.invalid", role=role)
            for name in ("satisfaction:manage_list", "documents:upload", "voting:manage_create"):
                with self.subTest(role=role, route=name):
                    self.client.force_login(actor)
                    expected = 200 if role in MANAGERS else 403
                    self.assertEqual(self.client.get(reverse(name)).status_code, expected)
                    self.assertEqual(self.post(actor, reverse(name), {}).status_code, expected)
        self.assertFalse(SatisfactionPeriod.objects.exists())
        self.assertFalse(Document.objects.exists())
        self.assertFalse(Vote.objects.exists())
        self.assertFalse(AuditEvent.objects.exists())

    def test_anonymous_get_and_post_redirect_to_login_without_mutation(self):
        client = Client(enforce_csrf_checks=True)
        client.get(reverse("communications:contact"))
        token = client.cookies[settings.CSRF_COOKIE_NAME].value
        for name in ("satisfaction:manage_list", "documents:upload", "voting:manage_create"):
            for response in (client.get(reverse(name)), client.post(reverse(name), {"csrfmiddlewaretoken": token})):
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.url.startswith(reverse("accounts:login")))
        self.assertFalse(AuditEvent.objects.exists())
