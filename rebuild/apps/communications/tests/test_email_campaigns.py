import smtplib
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from apps.core.models import AuditEvent
from apps.core.permissions import can, effective_role
from apps.core.tests.test_foundations import account
from apps.governance.models import Role, RoleGrant
from apps.members.models import MemberProfile
from apps.voting.models import Vote, VoteOption, Elector, Ballot, BallotSelection
from apps.voting.selectors import vote_results

from ..emailing import render_transactional
from ..models import MemberEmailCampaign, OutboxMessage
from ..outbox import deliver_batch
from ..selectors import campaign_recipients, with_tracking
from ..services import (broadcast_recipients, eligible_broadcast_members, queue_member_broadcast,
    resolve_broadcast_selection, retry_failed_broadcast)

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"


def named(email, first_name, last_name, role=Role.MEMBRE, **kwargs):
    user = account(email, role=role, **kwargs)
    user.first_name, user.last_name = first_name, last_name
    user.save(update_fields=["first_name", "last_name"])
    return user


class BroadcastTestCase(TestCase):
    """Club synthétique : quatre membres éligibles (président, Bureau, Anis, Rania) et
    trois comptes qui ne doivent jamais recevoir de communication."""

    def setUp(self):
        self.president = named("president-broadcast@example.invalid", "Test", "Président", role=Role.PRESIDENT)
        self.bureau = named("bureau-broadcast@example.invalid", "Test", "Bureau", role=Role.BUREAU)
        self.anis = named("anis-broadcast@example.invalid", "Anis", "Besbes")
        self.rania = named("rania-broadcast@example.invalid", "Rania", "Trabelsi")
        self.invite = account("invite-broadcast@example.invalid", role=Role.INVITE)
        self.suspended = account("suspended-broadcast@example.invalid", role=Role.MEMBRE)
        MemberProfile.objects.filter(user=self.suspended).update(status=MemberProfile.Status.SUSPENDED)
        self.inactive = account("inactive-broadcast@example.invalid", role=Role.MEMBRE, is_active=False)
        self.eligible = [self.president, self.bureau, self.anis, self.rania]
        self.url = reverse("communications:broadcast")
        self.client.force_login(self.president)

    def payload(self, action, members=(), **extra):
        data = {"subject": "Réunion mensuelle", "body": "Rendez-vous jeudi.", "campaign_key": str(uuid4()),
                "action": action, "members": [str(member.pk) for member in members], **extra}
        if action == "send":
            data.setdefault("confirmed", "yes")
        return data

    def post(self, action, members=(), **extra):
        return self.client.post(self.url, self.payload(action, members, **extra))

    def recipients(self):
        return sorted(OutboxMessage.objects.filter(kind="MEMBER_BROADCAST").values_list("recipient", flat=True))

    def queue(self, members=(), extra_emails=(), **kwargs):
        campaign, created = queue_member_broadcast(
            actor=self.president, subject=kwargs.pop("subject", "Réunion"), body=kwargs.pop("body", "Information."),
            idempotency_key=uuid4(), member_ids=[member.pk for member in members], extra_emails=list(extra_emails))
        self.assertTrue(created)
        return campaign


class EmailCampaignTests(BroadcastTestCase):
    """Sélection des destinataires : membres cochés et adresses externes, indépendants."""

    # A — un seul membre sélectionné
    def test_single_selected_member_is_the_only_recipient(self):
        response = self.post("send", [self.anis])
        campaign = MemberEmailCampaign.objects.get()
        self.assertRedirects(response, reverse("communications:broadcast_detail", args=[campaign.pk]))
        self.assertEqual(self.recipients(), [self.anis.email])
        self.assertEqual((campaign.recipient_count, campaign.internal_recipient_count, campaign.external_emails), (1, 1, []))
        self.assertEqual(campaign.audience, MemberEmailCampaign.Audience.SELECTION)

    # B — plusieurs membres sélectionnés
    def test_several_selected_members_are_the_only_recipients(self):
        self.post("send", [self.anis, self.rania])
        self.assertEqual(self.recipients(), sorted([self.anis.email, self.rania.email]))
        self.assertEqual(MemberEmailCampaign.objects.get().audience, MemberEmailCampaign.Audience.SELECTION)

    # C — tous les membres éligibles
    def test_all_eligible_members_selected(self):
        self.post("send", self.eligible)
        campaign = MemberEmailCampaign.objects.get()
        self.assertEqual(self.recipients(), sorted(member.email for member in self.eligible))
        self.assertEqual(campaign.recipient_count, 4)
        self.assertEqual(campaign.audience, MemberEmailCampaign.Audience.ALL_ACTIVE)

    def test_exact_responsibles_selection_is_labelled_as_such(self):
        self.post("send", [self.president, self.bureau])
        self.assertEqual(MemberEmailCampaign.objects.get().audience, MemberEmailCampaign.Audience.RESPONSIBLES)

    # D — uniquement une adresse externe : aucun membre ne reçoit rien
    def test_single_external_address_without_any_member(self):
        response = self.post("send", extra_emails="contact@example.invalid")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.recipients(), ["contact@example.invalid"])
        campaign = MemberEmailCampaign.objects.get()
        self.assertEqual((campaign.recipient_count, campaign.internal_recipient_count), (1, 0))
        self.assertEqual(campaign.external_emails, ["contact@example.invalid"])
        self.assertEqual(campaign.audience, MemberEmailCampaign.Audience.SELECTION)

    # E — plusieurs adresses externes sans membre
    def test_several_external_addresses_without_any_member(self):
        addresses = [f"partenaire{index}@example.invalid" for index in range(5)]
        self.post("send", extra_emails="\n".join(addresses))
        self.assertEqual(self.recipients(), sorted(addresses))
        self.assertEqual(MemberEmailCampaign.objects.get().internal_recipient_count, 0)

    # F — membres et adresses externes
    def test_members_and_external_addresses_are_combined(self):
        self.post("send", [self.president, self.anis, self.rania],
                  extra_emails="contact@example.invalid, partenaire@example.invalid")
        campaign = MemberEmailCampaign.objects.get()
        self.assertEqual((campaign.recipient_count, campaign.internal_recipient_count), (5, 3))
        self.assertEqual(len(self.recipients()), 5)
        self.assertNotIn(self.bureau.email, self.recipients())

    # G — aucun destinataire
    def test_no_recipient_is_rejected_with_a_clean_error(self):
        for action in ("confirm", "send"):
            with self.subTest(action=action):
                response = self.post(action)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Sélectionnez au moins un membre ou ajoutez une adresse externe.")
        self.assertEqual(MemberEmailCampaign.objects.count(), 0)
        self.assertEqual(OutboxMessage.objects.count(), 0)

    def test_service_refuses_an_empty_selection(self):
        with self.assertRaises(ValidationError):
            queue_member_broadcast(actor=self.president, subject="Réunion", body="Information.", idempotency_key=uuid4())
        self.assertEqual(MemberEmailCampaign.objects.count(), 0)

    # H — adresse externe invalide
    def test_invalid_external_addresses_are_rejected_with_a_clear_error(self):
        response = self.post("send", [self.anis], extra_emails="abc\ntest@\n@domain.com\nfoo bar")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Adresse(s) invalide(s)")
        self.assertEqual(MemberEmailCampaign.objects.count(), 0)
        self.assertEqual(OutboxMessage.objects.count(), 0)

    def test_more_than_fifty_external_addresses_is_rejected(self):
        many = ",".join(f"guest{i}@example.invalid" for i in range(51))
        response = self.post("confirm", extra_emails=many)
        self.assertContains(response, "50 adresses")
        self.assertEqual(MemberEmailCampaign.objects.count(), 0)

    # I — doublon externe/externe (insensible à la casse, espaces ignorés)
    def test_duplicate_external_addresses_collapse_to_one_recipient(self):
        self.post("send", extra_emails="  Partenaire@Example.invalid ,partenaire@example.invalid\npartenaire@example.invalid ")
        self.assertEqual(self.recipients(), ["Partenaire@Example.invalid"])
        self.assertEqual(MemberEmailCampaign.objects.get().recipient_count, 1)

    # J — doublon membre/externe
    def test_external_address_of_a_selected_member_is_sent_once(self):
        self.post("send", [self.anis], extra_emails=self.anis.email.upper())
        campaign = MemberEmailCampaign.objects.get()
        self.assertEqual(self.recipients(), [self.anis.email])
        self.assertEqual((campaign.recipient_count, campaign.internal_recipient_count, campaign.external_emails), (1, 1, []))

    def test_resolution_is_case_insensitive_between_members_and_external(self):
        members, external = resolve_broadcast_selection(
            [self.anis.pk], [self.anis.email.upper(), "Partenaire@Example.invalid", "partenaire@example.invalid"])
        self.assertEqual(members, [self.anis])
        self.assertEqual(external, ["Partenaire@Example.invalid"])

    # K — permission refusée
    def test_permission_is_unchanged_and_enforced_on_every_entry_point(self):
        self.assertTrue(can(self.president, "communication.send_member_broadcast"))
        self.assertTrue(can(self.bureau, "communication.send_member_broadcast"))
        self.assertFalse(can(self.anis, "communication.send_member_broadcast"))
        campaign = self.queue([self.rania])
        self.client.force_login(self.anis)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.post("send", [self.rania]).status_code, 403)
        self.assertEqual(self.client.get(reverse("communications:broadcast_history")).status_code, 403)
        detail = reverse("communications:broadcast_detail", args=[campaign.pk])
        self.assertEqual(self.client.get(detail).status_code, 403)
        self.assertEqual(self.client.post(detail).status_code, 403)
        self.assertEqual(MemberEmailCampaign.objects.count(), 1)
        with self.assertRaises(PermissionDenied):
            queue_member_broadcast(actor=self.anis, subject="Réunion", body="Information.",
                                   idempotency_key=uuid4(), member_ids=[self.rania.pk])
        with self.assertRaises(PermissionDenied):
            retry_failed_broadcast(actor=self.anis, campaign=campaign)

    # L — personnalisation membre
    @override_settings(EMAIL_BACKEND=LOCMEM)
    def test_member_email_is_personalized_with_first_name(self):
        self.post("send", [self.anis, self.rania])
        self.assertEqual(deliver_batch(limit=20)["failed"], 0)
        self.assertEqual(len(mail.outbox), 2)
        anis_mail = next(message for message in mail.outbox if message.to == [self.anis.email])
        rania_mail = next(message for message in mail.outbox if message.to == [self.rania.email])
        self.assertIn("Bonjour Anis,", strip_tags(anis_mail.alternatives[0].content))
        self.assertIn("Bonjour Anis,", anis_mail.body)
        self.assertIn("Bonjour Rania,", strip_tags(rania_mail.alternatives[0].content))

    # M — personnalisation externe
    @override_settings(EMAIL_BACKEND=LOCMEM)
    def test_external_address_without_account_gets_generic_greeting(self):
        self.queue(extra_emails=["partenaire@example.invalid"])
        self.assertEqual(deliver_batch(limit=10)["failed"], 0)
        self.assertEqual([message.to for message in mail.outbox], [["partenaire@example.invalid"]])
        html = strip_tags(mail.outbox[0].alternatives[0].content)
        self.assertIn("Bonjour,", html)
        self.assertNotIn("Bonjour ,", html)
        self.assertIn("Bonjour,", mail.outbox[0].body)

    @override_settings(EMAIL_BACKEND=LOCMEM)
    def test_external_address_matching_an_unselected_member_is_personalized(self):
        # Rania n'est pas cochée, mais son adresse est saisie à la main : un seul message,
        # envoyé à l'adresse telle que saisie, avec son prénom (voir emailing.recipient_for_email).
        self.queue([self.anis], extra_emails=[self.rania.email.upper()])
        self.assertEqual(deliver_batch(limit=10)["failed"], 0)
        self.assertEqual(len(mail.outbox), 2)
        rania_mail = next(message for message in mail.outbox if message.to == [self.rania.email.upper()])
        self.assertIn("Bonjour Rania", strip_tags(rania_mail.alternatives[0].content))

    # N — création correcte des OutboxMessage
    def test_outbox_messages_are_created_one_per_recipient(self):
        campaign = self.queue([self.anis, self.rania], extra_emails=["contact@example.invalid"])
        rows = OutboxMessage.objects.filter(kind="MEMBER_BROADCAST", object_id=campaign.pk)
        self.assertEqual(rows.count(), 3)
        self.assertEqual(OutboxMessage.objects.count(), 3)
        self.assertEqual(set(rows.values_list("state", "attempts", "error_code")), {("PENDING", 0, "")})
        self.assertEqual(rows.get(recipient=self.anis.email).event_key, f"broadcast:{campaign.pk}:{self.anis.pk}")
        self.assertEqual(rows.get(recipient=self.rania.email).event_key, f"broadcast:{campaign.pk}:{self.rania.pk}")
        self.assertTrue(rows.get(recipient="contact@example.invalid").event_key.startswith(f"broadcast:{campaign.pk}:ext:"))
        self.assertEqual((campaign.recipient_count, campaign.queued_count), (3, 3))
        self.assertTrue(AuditEvent.objects.filter(action="communication.member_broadcast_queued", object_id=str(campaign.pk)).exists())

    # Q — protection double-submit
    def test_double_submission_creates_a_single_campaign_and_no_second_email(self):
        data = self.payload("send", [self.anis, self.rania], extra_emails="contact@example.invalid")
        responses = [self.client.post(self.url, data) for _ in range(3)]
        campaign = MemberEmailCampaign.objects.get()
        detail = reverse("communications:broadcast_detail", args=[campaign.pk])
        for response in responses:
            self.assertRedirects(response, detail)
        self.assertEqual(OutboxMessage.objects.filter(kind="MEMBER_BROADCAST").count(), 3)
        self.assertEqual(AuditEvent.objects.filter(action="communication.member_broadcast_queued").count(), 1)

    def test_replayed_key_never_sends_a_different_selection(self):
        data = self.payload("send", [self.anis])
        self.client.post(self.url, data)
        data["members"] = [str(member.pk) for member in self.eligible]
        self.client.post(self.url, data)
        self.assertEqual(MemberEmailCampaign.objects.count(), 1)
        self.assertEqual(self.recipients(), [self.anis.email])

    # R — aucune fuite CC/BCC, un destinataire par message
    @override_settings(EMAIL_BACKEND=LOCMEM)
    def test_never_more_than_one_recipient_per_message_no_cc_or_bcc(self):
        self.queue(self.eligible, extra_emails=["contact@example.invalid", "partenaire@example.invalid"])
        self.assertEqual(deliver_batch(limit=20), {"sent": 6, "failed": 0, "disabled": False})
        self.assertEqual(len(mail.outbox), 6)
        addresses = {member.email for member in self.eligible} | {"contact@example.invalid", "partenaire@example.invalid"}
        for message in mail.outbox:
            self.assertEqual(len(message.to), 1)
            self.assertEqual(message.cc, [])
            self.assertEqual(message.bcc, [])
            self.assertEqual(message.recipients(), message.to)
            others = addresses - set(message.to)
            content = message.body + message.alternatives[0].content + str(message.message())
            self.assertFalse([address for address in others if address in content])

    # S — comptes inéligibles impossibles à forcer par une requête fabriquée
    def test_forged_post_cannot_target_ineligible_or_unknown_accounts(self):
        for forged in (self.invite.pk, self.suspended.pk, self.inactive.pk, uuid4(), "not-a-uuid"):
            with self.subTest(forged=forged):
                data = self.payload("send", [self.anis])
                data["members"].append(str(forged))
                response = self.client.post(self.url, data)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "n’est plus disponible pour la communication")
                self.assertEqual(MemberEmailCampaign.objects.count(), 0)
                self.assertEqual(OutboxMessage.objects.count(), 0)

    def test_service_rejects_ineligible_member_ids_even_without_the_form(self):
        for forged in (self.invite.pk, self.suspended.pk, self.inactive.pk, uuid4()):
            with self.subTest(forged=forged), self.assertRaises(ValidationError):
                queue_member_broadcast(actor=self.president, subject="Réunion", body="Information.",
                                       idempotency_key=uuid4(), member_ids=[self.anis.pk, forged])
        self.assertEqual(MemberEmailCampaign.objects.count(), 0)
        self.assertEqual(OutboxMessage.objects.count(), 0)

    def test_external_field_cannot_reach_a_known_ineligible_account(self):
        for blocked in (self.invite, self.suspended, self.inactive):
            for action in ("confirm", "send"):
                with self.subTest(blocked=blocked.email, action=action):
                    # Casse et espaces différents : même compte, même refus.
                    response = self.post(action, [self.anis], extra_emails=f"  {blocked.email.upper()} \ncontact@example.invalid")
                    self.assertEqual(response.status_code, 200)
                    self.assertTemplateUsed(response, "espace/communication_broadcast.html")
                    self.assertContains(response, "appartient à un compte du club qui ne peut pas recevoir de communication")
                    self.assertEqual(MemberEmailCampaign.objects.count(), 0)
                    self.assertEqual(OutboxMessage.objects.count(), 0)

    def test_service_refuses_a_known_ineligible_account_as_external_address(self):
        for blocked in (self.invite, self.suspended, self.inactive):
            with self.subTest(blocked=blocked.email), self.assertRaises(ValidationError):
                queue_member_broadcast(actor=self.president, subject="Réunion", body="Information.",
                                       idempotency_key=uuid4(), extra_emails=[blocked.email.upper()])
        self.assertEqual(MemberEmailCampaign.objects.count(), 0)
        self.assertEqual(OutboxMessage.objects.count(), 0)

    def test_unknown_external_address_and_eligible_member_address_stay_allowed(self):
        # Véritable adresse externe, et adresse d'un membre éligible simplement non coché.
        response = self.post("send", extra_emails=f"inconnu@example.invalid, {self.rania.email}")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.recipients(), sorted(["inconnu@example.invalid", self.rania.email]))

    def test_member_who_became_ineligible_before_sending_blocks_the_send(self):
        data = self.payload("send", [self.anis, self.rania])
        MemberProfile.objects.filter(user=self.rania).update(status=MemberProfile.Status.SUSPENDED)
        response = self.client.post(self.url, data)
        self.assertContains(response, "n’est plus disponible pour la communication")
        self.assertEqual(OutboxMessage.objects.count(), 0)


class CompositionPageTests(BroadcastTestCase):
    """Rédaction → vérification → envoi : rien ne part avant la confirmation."""

    def test_page_lists_only_eligible_members_as_real_checkboxes(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        for member in self.eligible:
            self.assertContains(response, f'<input type="checkbox" name="members" value="{member.pk}"')
            self.assertContains(response, member.email)
        for excluded in (self.invite, self.suspended, self.inactive):
            self.assertNotContains(response, str(excluded.pk))
            self.assertNotContains(response, excluded.email)
        self.assertNotContains(response, " checked")  # rien n'est présélectionné
        self.assertContains(response, "Tout sélectionner")
        self.assertContains(response, "Vérifier l’envoi")
        self.assertNotContains(response, ">Continuer<")
        self.assertContains(response, 'data-responsible', count=2)  # président et Bureau

    def test_preview_never_queues_or_sends_and_sanitizes_html(self):
        response = self.post("preview", [self.anis], body="Bonjour <script>alert(1)</script> à tous.")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aperçu du message")
        self.assertNotContains(response, "<script>alert", html=False)
        self.assertEqual(MemberEmailCampaign.objects.count(), 0)
        self.assertEqual(OutboxMessage.objects.count(), 0)

    def test_preview_does_not_require_recipients_and_keeps_the_selection(self):
        self.assertContains(self.post("preview"), "Aperçu du message")
        response = self.post("preview", [self.rania])
        self.assertContains(response, f'value="{self.rania.pk}" data-member data-email="{self.rania.email}" checked')
        self.assertContains(response, " checked", count=1)

    def test_preview_srcdoc_attribute_is_properly_escaped(self):
        # render_to_string() renvoie une SafeString : le filtre `escape` (conditional_escape)
        # ne fait alors rien, ce qui laissait échapper un `"` brut dans l'attribut srcdoc
        # (ex. `<html lang="fr">`) et cassait le HTML de la page hôte à cet endroit précis.
        # `force_escape` échappe sans condition, y compris une valeur déjà marquée safe.
        html = self.post("preview", [self.anis]).content.decode()
        self.assertIn('srcdoc="&lt;!doctype html&gt;', html)
        # L'attribut doit se refermer proprement juste avant class="email-preview-frame" :
        # s'il s'était rouvert prématurément (bug), ce motif exact n'apparaîtrait pas.
        self.assertIn('&lt;/html&gt;\n" class="email-preview-frame">', html)

    def test_preview_shows_a_second_generic_preview_when_external_addresses_present(self):
        response = self.post("preview", [self.anis], extra_emails="partenaire@example.invalid")
        self.assertContains(response, "Aperçu pour une adresse externe")
        self.assertEqual(response.content.decode().count('srcdoc="&lt;!doctype html&gt;'), 2)

    @override_settings(EMAIL_BACKEND=LOCMEM)
    def test_test_email_goes_only_to_the_author_and_keeps_the_draft(self):
        response = self.post("test", [self.anis, self.rania], extra_emails="contact@example.invalid")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([message.to for message in mail.outbox], [[self.president.email]])
        self.assertContains(response, "E-mail test envoyé uniquement à votre adresse.")
        self.assertContains(response, " checked", count=2)
        self.assertContains(response, "contact@example.invalid")
        self.assertContains(response, 'value="Réunion mensuelle"')
        self.assertEqual(MemberEmailCampaign.objects.count(), 0)
        self.assertEqual(OutboxMessage.objects.count(), 0)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.dummy.EmailBackend")
    def test_test_email_never_claims_success_when_delivery_is_disabled(self):
        response = self.post("test", [self.anis])
        self.assertContains(response, "aucun test n’a été envoyé")
        self.assertNotContains(response, "E-mail test envoyé uniquement")
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_BACKEND=LOCMEM)
    def test_test_email_failure_is_reported(self):
        with patch("apps.communications.views.EmailMultiAlternatives.send", return_value=0):
            response = self.post("test", [self.anis])
        self.assertContains(response, "Le test n’a pas pu être envoyé.")
        self.assertContains(response, " checked", count=1)

    def test_confirmation_step_names_recipients_and_sends_nothing(self):
        response = self.post("confirm", [self.anis, self.rania], extra_emails="contact@example.invalid")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "espace/communication_confirm.html")
        self.assertContains(response, "Votre message est prêt à être envoyé")
        self.assertContains(response, "Envoyer à 3 destinataires")
        self.assertContains(response, "2 membres sélectionnés")
        self.assertContains(response, "1 adresse externe")
        for text in ("Anis Besbes", "Rania Trabelsi", "contact@example.invalid", "Réunion mensuelle"):
            self.assertContains(response, text)
        self.assertNotContains(response, "Test Bureau")
        self.assertContains(response, ">Modifier<")
        self.assertEqual(MemberEmailCampaign.objects.count(), 0)
        self.assertEqual(OutboxMessage.objects.count(), 0)

    def test_confirmation_button_is_singular_for_one_recipient(self):
        self.assertContains(self.post("confirm", extra_emails="contact@example.invalid"), "Envoyer à 1 destinataire<")

    def test_confirmation_reports_ignored_duplicates(self):
        response = self.post("confirm", [self.anis], extra_emails=f"{self.anis.email.upper()}, a@example.invalid, A@example.invalid")
        self.assertContains(response, "2 adresses en double ignorées")
        self.assertContains(response, "Envoyer à 2 destinataires")

    def test_send_requires_the_confirmation_step(self):
        response = self.post("send", [self.anis], confirmed="no")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "espace/communication_broadcast.html")
        self.assertEqual(OutboxMessage.objects.count(), 0)

    def test_back_from_confirmation_restores_the_draft(self):
        response = self.post("back", [self.anis], extra_emails="contact@example.invalid")
        self.assertTemplateUsed(response, "espace/communication_broadcast.html")
        self.assertContains(response, " checked", count=1)
        self.assertContains(response, "contact@example.invalid")
        self.assertEqual(OutboxMessage.objects.count(), 0)


class CampaignTrackingTests(BroadcastTestCase):
    """Historique et suivi par destinataire, lus dans l'outbox existante."""

    def set_state(self, campaign, recipient, **values):
        OutboxMessage.objects.filter(object_id=campaign.pk, recipient=recipient).update(**values)

    def mixed_campaign(self):
        campaign = self.queue([self.anis, self.rania, self.bureau], extra_emails=["contact@example.invalid"],
                              subject="Assemblée générale")
        self.set_state(campaign, self.anis.email, state="SENT", attempts=1, sent_at=timezone.now())
        self.set_state(campaign, "contact@example.invalid", state="FAILED", attempts=5, error_code="recipient_refused")
        self.set_state(campaign, self.bureau.email, state="FAILED", attempts=1, error_code="not_applicable")
        return campaign  # Rania reste PENDING

    # O — historique des campagnes
    def test_history_lists_campaigns_with_real_counters_and_no_address_leak(self):
        campaign = self.mixed_campaign()
        response = self.client.get(reverse("communications:broadcast_history"))
        self.assertEqual(response.status_code, 200)
        for text in ("Assemblée générale", "Test Président", "4 destinataires", "1 envoyé", "1 en attente",
                     "2 échecs", "En cours", "3 membres", "1 adresse externe", "Voir le détail"):
            self.assertContains(response, text)
        self.assertContains(response, reverse("communications:broadcast_detail", args=[campaign.pk]))
        self.assertNotContains(response, "contact@example.invalid")
        self.assertNotContains(response, self.anis.email)

    def test_empty_history_has_a_real_empty_state(self):
        response = self.client.get(reverse("communications:broadcast_history"))
        self.assertContains(response, "Aucune communication envoyée pour l’instant.")

    # P — PENDING / SENT / FAILED par destinataire
    def test_detail_shows_each_recipient_state(self):
        campaign = self.mixed_campaign()
        rows = {row["email"]: row for row in campaign_recipients(campaign)}
        self.assertEqual(len(rows), 4)
        self.assertEqual((rows[self.anis.email]["state"], rows[self.anis.email]["name"]), ("sent", "Anis Besbes"))
        self.assertIsNotNone(rows[self.anis.email]["at"])
        self.assertEqual((rows[self.rania.email]["state"], rows[self.rania.email]["label"]), ("pending", "En attente"))
        external = rows["contact@example.invalid"]
        self.assertEqual((external["state"], external["external"], external["name"], external["attempts"]), ("failed", True, "", 5))
        self.assertTrue(external["retryable"])
        self.assertIn("refusée", external["reason"])
        self.assertFalse(rows[self.bureau.email]["retryable"])  # refus métier définitif
        self.assertIn("Compte désactivé", rows[self.bureau.email]["reason"])
        # Les problèmes d'abord, les envois réussis en dernier.
        self.assertEqual([row["state"] for row in campaign_recipients(campaign)], ["failed", "failed", "pending", "sent"])

        response = self.client.get(reverse("communications:broadcast_detail", args=[campaign.pk]))
        self.assertEqual(response.status_code, 200)
        for text in ("Anis Besbes", "Rania Trabelsi", "contact@example.invalid", "Envoyé", "En attente", "Échec",
                     "5 tentatives", "Adresse refusée par le serveur de messagerie", "le serveur de messagerie a accepté le message",
                     "Réessayer l’échec"):
            self.assertContains(response, text)
        for forbidden in ("Délivré", "Traceback", "recipient_refused", "not_applicable"):
            self.assertNotContains(response, forbidden)

    def test_overall_status_is_computed_from_the_outbox(self):
        cases = [("En cours", {}), ("Terminé", {"state": "SENT"}), ("Échec", {"state": "FAILED", "error_code": "delivery_failed"})]
        for expected, values in cases:
            with self.subTest(expected=expected):
                campaign = self.queue([self.anis, self.rania])
                OutboxMessage.objects.filter(object_id=campaign.pk).update(**values)
                self.assertEqual(with_tracking([campaign])[0].tracking["status_label"], expected)
        campaign = self.queue([self.anis, self.rania])
        self.set_state(campaign, self.anis.email, state="SENT")
        self.set_state(campaign, self.rania.email, state="FAILED", error_code="delivery_failed")
        tracking = with_tracking([campaign])[0].tracking
        self.assertEqual((tracking["status_label"], tracking["sent"], tracking["failed"], tracking["pending"], tracking["total"]),
                         ("Terminé avec erreurs", 1, 1, 0, 2))
        self.set_state(campaign, self.rania.email, state="SENDING")
        self.assertEqual(with_tracking([campaign])[0].tracking["status_label"], "En cours")

    @override_settings(EMAIL_BACKEND=LOCMEM)
    def test_real_delivery_moves_recipients_from_pending_to_sent(self):
        campaign = self.queue([self.anis], extra_emails=["contact@example.invalid"])
        self.assertEqual({row["state"] for row in campaign_recipients(campaign)}, {"pending"})
        deliver_batch(limit=10)
        self.assertEqual({row["state"] for row in campaign_recipients(campaign)}, {"sent"})
        campaign.refresh_from_db()
        self.assertEqual((campaign.status, campaign.sent_count, campaign.failed_count), ("SENT", 2, 0))

    @override_settings(EMAIL_BACKEND=LOCMEM)
    def test_refused_recipient_gets_a_readable_reason_and_keeps_the_retry_policy(self):
        campaign = self.queue(extra_emails=["inconnu@example.invalid"])
        refusal = smtplib.SMTPRecipientsRefused({"inconnu@example.invalid": (550, b"sensitive SMTP detail")})
        with patch("apps.communications.outbox.EmailMultiAlternatives.send", side_effect=refusal):
            self.assertEqual(deliver_batch(limit=5)["failed"], 1)
        item = OutboxMessage.objects.get(object_id=campaign.pk)
        self.assertEqual((item.state, item.error_code, item.attempts), ("PENDING", "recipient_refused", 1))
        row = campaign_recipients(campaign)[0]
        self.assertEqual((row["state"], row["attempts"]), ("pending", 1))
        self.assertIn("nouvelle tentative", row["reason"])
        response = self.client.get(reverse("communications:broadcast_detail", args=[campaign.pk]))
        self.assertNotContains(response, "sensitive SMTP detail")

    # Relance manuelle des échecs de livraison
    def test_retry_requeues_only_delivery_failures_in_the_existing_outbox(self):
        campaign = self.mixed_campaign()
        before = dict(OutboxMessage.objects.filter(object_id=campaign.pk).values_list("recipient", "pk"))
        keys = dict(OutboxMessage.objects.filter(object_id=campaign.pk).values_list("recipient", "event_key"))
        detail = reverse("communications:broadcast_detail", args=[campaign.pk])
        self.assertRedirects(self.client.post(detail), detail)
        rows = {item.recipient: item for item in OutboxMessage.objects.filter(object_id=campaign.pk)}
        self.assertEqual(len(rows), 4)  # aucune ligne créée
        self.assertEqual({recipient: item.pk for recipient, item in rows.items()}, before)
        self.assertEqual({recipient: item.event_key for recipient, item in rows.items()}, keys)
        retried = rows["contact@example.invalid"]
        self.assertEqual((retried.state, retried.attempts, retried.error_code), ("PENDING", 0, ""))
        self.assertEqual(rows[self.anis.email].state, "SENT")  # jamais renvoyé
        self.assertEqual((rows[self.bureau.email].state, rows[self.bureau.email].error_code), ("FAILED", "not_applicable"))
        self.assertEqual(AuditEvent.objects.filter(action="communication.member_broadcast_retried", object_id=str(campaign.pk)).count(), 1)
        # Second clic : plus rien à relancer, aucune seconde trace d'audit.
        self.assertEqual(retry_failed_broadcast(actor=self.president, campaign=campaign), 0)
        self.assertEqual(AuditEvent.objects.filter(action="communication.member_broadcast_retried").count(), 1)

    @override_settings(EMAIL_BACKEND=LOCMEM)
    def test_retried_message_is_delivered_once_by_the_regular_worker(self):
        campaign = self.queue([self.anis])
        self.set_state(campaign, self.anis.email, state="FAILED", attempts=5, error_code="delivery_failed")
        self.assertEqual(retry_failed_broadcast(actor=self.president, campaign=campaign), 1)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "QUEUED")
        self.assertEqual(deliver_batch(limit=5), {"sent": 1, "failed": 0, "disabled": False})
        self.assertEqual(deliver_batch(limit=5)["sent"], 0)
        self.assertEqual([message.to for message in mail.outbox], [[self.anis.email]])
        campaign.refresh_from_db()
        self.assertEqual((campaign.status, campaign.sent_count, campaign.failed_count), ("SENT", 1, 0))

    def test_detail_never_exposes_raw_smtp_or_technical_details(self):
        campaign = self.queue([self.anis, self.rania, self.bureau, self.president], extra_emails=["contact@example.invalid"])
        with override_settings(EMAIL_BACKEND=LOCMEM), patch(
                "apps.communications.outbox.EmailMultiAlternatives.send",
                side_effect=OSError("550 5.1.1 mailbox unavailable smtp.internal.example password=secret")):
            deliver_batch(limit=10)
        self.set_state(campaign, self.rania.email, state="FAILED", attempts=5, error_code="attempt_limit")
        self.set_state(campaign, self.bureau.email, state="FAILED", attempts=1, error_code="not_applicable")
        self.set_state(campaign, self.president.email, state="FAILED", attempts=5, error_code="recipient_refused")
        self.set_state(campaign, "contact@example.invalid", state="FAILED", attempts=3, error_code="code_inconnu")
        self.assertEqual(OutboxMessage.objects.get(object_id=campaign.pk, recipient=self.anis.email).error_code, "delivery_failed")
        rows = {row["email"]: row for row in campaign_recipients(campaign)}
        self.assertEqual(rows["contact@example.invalid"]["reason"], "L’envoi a échoué.")  # code inconnu : raison générique
        self.assertFalse(rows["contact@example.invalid"]["retryable"])
        response = self.client.get(reverse("communications:broadcast_detail", args=[campaign.pk]))
        for reason in ("Nombre maximal de tentatives atteint.", "Compte désactivé ou adresse modifiée",
                       "Adresse refusée par le serveur de messagerie", "L’envoi a échoué."):
            self.assertContains(response, reason)
        for forbidden in ("mailbox unavailable", "smtp.internal.example", "password=secret", "OSError", "Traceback",
                          "delivery_failed", "attempt_limit", "not_applicable", "recipient_refused", "code_inconnu",
                          "event_key", "broadcast:"):
            self.assertNotContains(response, forbidden)

    def test_retry_help_mentions_the_exceptional_duplicate_risk(self):
        campaign = self.mixed_campaign()
        response = self.client.get(reverse("communications:broadcast_detail", args=[campaign.pk]))
        self.assertContains(response, "Exceptionnellement, un destinataire peut recevoir le message en double")

    def test_navigation_keeps_communication_active_on_every_page_of_the_module(self):
        campaign = self.queue([self.anis])
        link = 'class="app-nav__lien actif" href="/espace/communication/"'
        pages = [(self.url, 'aria-current="page"'), (reverse("communications:broadcast_history"), 'aria-current="true"'),
                 (reverse("communications:broadcast_detail", args=[campaign.pk]), 'aria-current="true"')]
        for path, current in pages:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertContains(response, f'{link} aria-label="Communication" {current}>')
                self.assertContains(response, "app-nav__lien actif", count=1)
        # Ailleurs dans l'espace, l'entrée redevient un lien ordinaire.
        other = self.client.get(reverse("notifications:list"))
        self.assertContains(other, 'class="app-nav__lien" href="/espace/communication/" aria-label="Communication">')

    def test_unknown_campaign_detail_is_not_found(self):
        self.assertEqual(self.client.get(reverse("communications:broadcast_detail", args=[uuid4()])).status_code, 404)


class OtherTransactionalEmailTests(TestCase):
    def setUp(self):
        self.president = account("president-mails@example.invalid", role=Role.PRESIDENT)
        self.member = account("member-mails@example.invalid", role=Role.MEMBRE)

    def test_vote_result_email_uses_aggregate_result_without_ballot_identity(self):
        vote = Vote.objects.create(title="Vote test", status=Vote.Status.CLOSED, mode=Vote.Mode.SINGLE,
                                   min_choices=1, max_choices=1, opens_at=timezone.now(), responsible=self.president)
        option_a = VoteOption.objects.create(vote=vote, label="Option A", order=1)
        option_b = VoteOption.objects.create(vote=vote, label="Option B", order=2)
        elector = Elector.objects.create(vote=vote, profile=self.member.member_profile)
        ballots = [Ballot.objects.create(vote=vote) for _ in range(24)]
        for ballot in ballots[:14]:
            BallotSelection.objects.create(ballot=ballot, option=option_a)
        for ballot in ballots[14:]:
            BallotSelection.objects.create(ballot=ballot, option=option_b)
        # Résultat officiel : même moteur que la page, sans électeur ni bulletin transmis au modèle.
        results = vote_results(self.member, vote)
        _, text_body, html_body = render_transactional("VOTE_RESULTS", user=self.member, vote=vote, results=results)
        self.assertIn("Option A", html_body)
        self.assertIn("14 voix", html_body)
        self.assertIn("58,3 %", html_body)
        self.assertIn("10 voix", html_body)
        self.assertIn("41,7 %", html_body)
        self.assertIn("24 votes exprimés", html_body)
        self.assertNotIn(str(elector.pk), html_body + text_body)
        self.assertNotIn(str(ballots[0].pk), html_body + text_body)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", SITE_ORIGIN="https://lionsmed.example")
    def test_activation_email_is_personalized_and_uses_an_absolute_secure_logo(self):
        newcomer = account("nouveau@example.invalid", role=Role.MEMBRE)
        newcomer.first_name = "Sana"
        newcomer.set_unusable_password()
        newcomer.save(update_fields=["first_name", "password"])
        OutboxMessage.objects.create(
            event_key=f"activation-test:{newcomer.pk}", kind="ACTIVATION",
            recipient=newcomer.email, object_id=newcomer.pk,
        )
        report = deliver_batch(limit=1)
        self.assertEqual(report, {"sent": 1, "failed": 0, "disabled": False})
        self.assertEqual(mail.outbox[0].to, [newcomer.email])
        html = mail.outbox[0].alternatives[0].content
        self.assertIn("Bonjour Sana", strip_tags(html))
        self.assertIn("https://lionsmed.example/static/images/emblem-256.png", html)
        self.assertIn("Activer mon espace membre", html)
        self.assertIn("District 414 Tunisie", html)


class EligibilityTests(TestCase):
    """Éligibilité résolue via effective_role(), jamais une liste de rôles recopiée à la
    main — voir apps.communications.services.eligible_broadcast_members. C'est aussi la
    définition de « Tout sélectionner »."""

    def setUp(self):
        self.president = account("president-audience@example.invalid", role=Role.PRESIDENT)
        self.member = account("member-audience@example.invalid", role=Role.MEMBRE)
        self.invite = account("invite-audience@example.invalid", role=Role.INVITE)
        self.gmt = account("gmt-audience@example.invalid", role=Role.GMT)
        self.marketing = account("marketing-audience@example.invalid", role=Role.MARKETING_COMMUNICATION)
        self.inactive = account("inactive-audience@example.invalid", role=Role.MEMBRE, is_active=False)
        self.suspended = account("suspended-audience@example.invalid", role=Role.MEMBRE)
        MemberProfile.objects.filter(user=self.suspended).update(status=MemberProfile.Status.SUSPENDED)
        # Deux grants actifs simultanément (le second avec une révocation programmée dans
        # le futur, donc non couvert par l'exclusion DB qui ne porte que sur revoked_at
        # NULL) : rôle effectif ambigu, effective_role() refuse de trancher.
        self.ambiguous = account("ambiguous-audience@example.invalid", role=Role.BUREAU)
        RoleGrant.objects.create(user=self.ambiguous, role=Role.GLT,
            starts_at=timezone.now() - timedelta(hours=1), revoked_at=timezone.now() + timedelta(hours=1))

    def test_ambiguous_role_is_never_resolved(self):
        self.assertIsNone(effective_role(self.ambiguous))

    def test_eligible_members_are_exactly_the_active_resolvable_non_guest_accounts(self):
        eligible = {user for user, _ in eligible_broadcast_members()}
        self.assertEqual(eligible, {self.president, self.member, self.gmt, self.marketing})
        self.assertEqual(set(broadcast_recipients()), eligible)  # annonces d'agenda : même périmètre

    def test_responsibles_excludes_membre_and_invite_but_keeps_every_other_role(self):
        recipients = broadcast_recipients(MemberEmailCampaign.Audience.RESPONSIBLES)
        self.assertEqual(set(recipients), {self.president, self.gmt, self.marketing})  # suit effective_role()

    def test_selection_audience_is_not_a_group(self):
        with self.assertRaises(ValidationError):
            broadcast_recipients(MemberEmailCampaign.Audience.SELECTION)

    def test_select_all_shortcut_cannot_reach_ineligible_accounts(self):
        self.client.force_login(self.president)
        response = self.client.get(reverse("communications:broadcast"))
        self.assertContains(response, 'name="members"', count=4)
        for excluded in (self.invite, self.inactive, self.suspended, self.ambiguous):
            self.assertNotContains(response, excluded.email)
