from datetime import timedelta
from uuid import uuid4

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from apps.core.permissions import can, effective_role
from apps.core.tests.test_foundations import account
from apps.governance.models import Role, RoleGrant
from apps.members.models import MemberProfile
from apps.voting.models import Vote, VoteOption, Elector, Ballot, BallotSelection
from apps.voting.selectors import vote_results

from ..emailing import render_transactional
from ..models import MemberEmailCampaign, OutboxMessage
from ..outbox import deliver_batch
from ..services import broadcast_recipients, resolve_broadcast_recipients, queue_member_broadcast


class EmailCampaignTests(TestCase):
    def setUp(self):
        self.president = account("president-broadcast@example.invalid", role=Role.PRESIDENT)
        self.member = account("member-broadcast@example.invalid", role=Role.MEMBRE)
        self.member.first_name = "Anis"
        self.member.save(update_fields=["first_name"])
        self.invite = account("invite-broadcast@example.invalid", role=Role.INVITE)
        self.suspended = account("suspended-broadcast@example.invalid", role=Role.MEMBRE)
        MemberProfile.objects.filter(user=self.suspended).update(status=MemberProfile.Status.SUSPENDED)
        self.bureau = account("bureau-broadcast@example.invalid", role=Role.BUREAU)
        self.member_url = reverse("communications:broadcast")

    def post(self, actor, action, **extra):
        self.client.force_login(actor)
        payload = {"subject": "Réunion mensuelle", "body": "Bonjour <script>alert(1)</script> à tous.",
                   "campaign_key": str(uuid4()), "action": action, "audience": "ALL_ACTIVE", **extra}
        return self.client.post(self.member_url, payload)

    def test_only_bureau_roles_have_explicit_capability_and_navigation(self):
        self.assertTrue(can(self.president, "communication.send_member_broadcast"))
        self.assertTrue(can(self.bureau, "communication.send_member_broadcast"))
        self.assertFalse(can(self.member, "communication.send_member_broadcast"))
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(self.member_url).status_code, 403)

    def test_preview_never_queues_or_sends_and_sanitizes_html(self):
        response = self.post(self.president, "preview")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aperçu")
        self.assertNotContains(response, "<script>", html=False)
        self.assertEqual(MemberEmailCampaign.objects.count(), 0)
        self.assertEqual(OutboxMessage.objects.count(), 0)

    def test_preview_srcdoc_attribute_is_properly_escaped(self):
        # render_to_string() renvoie une SafeString : le filtre `escape` (conditional_escape)
        # ne fait alors rien, ce qui laissait échapper un `"` brut dans l'attribut srcdoc
        # (ex. `<html lang="fr">`) et cassait le HTML de la page hôte à cet endroit précis.
        # `force_escape` échappe sans condition, y compris une valeur déjà marquée safe.
        response = self.post(self.president, "preview")
        html = response.content.decode()
        self.assertIn('srcdoc="&lt;!doctype html&gt;', html)
        # L'attribut doit se refermer proprement juste avant class="email-preview-frame" :
        # s'il s'était rouvert prématurément (bug), ce motif exact n'apparaîtrait pas.
        self.assertIn('&lt;/html&gt;\n" class="email-preview-frame">', html)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_test_email_is_sent_only_to_author(self):
        response = self.post(self.president, "test")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.president.email])
        self.assertEqual(MemberEmailCampaign.objects.count(), 0)

    def test_confirmed_campaign_is_individual_idempotent_and_excludes_non_members(self):
        key = str(uuid4())
        self.client.force_login(self.president)
        data = {"subject": "Réunion mensuelle", "body": "Information importante", "campaign_key": key,
                "action": "send", "confirmed": "yes", "audience": "ALL_ACTIVE"}
        first = self.client.post(self.member_url, data)
        second = self.client.post(self.member_url, data)
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        campaign = MemberEmailCampaign.objects.get()
        self.assertEqual(campaign.recipient_count, 3)  # président, membre et Bureau ; invité/suspendu exclus
        recipients = set(OutboxMessage.objects.filter(kind="MEMBER_BROADCAST").values_list("recipient", flat=True))
        self.assertNotIn(self.invite.email, recipients)
        self.assertNotIn(self.suspended.email, recipients)
        self.assertEqual(len(recipients), campaign.recipient_count)
        self.assertEqual(OutboxMessage.objects.filter(kind="MEMBER_BROADCAST").count(), campaign.recipient_count)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_outbox_renders_one_personalized_email_per_member(self):
        self.client.force_login(self.president)
        response = self.client.post(self.member_url, {
            "subject": "Réunion", "body": "Rendez-vous jeudi.", "campaign_key": str(uuid4()),
            "action": "send", "confirmed": "yes", "audience": "ALL_ACTIVE",
        })
        self.assertEqual(response.status_code, 302)
        report = deliver_batch(limit=20)
        self.assertEqual(report["failed"], 0)
        self.assertEqual(len(mail.outbox), MemberEmailCampaign.objects.get().recipient_count)
        self.assertTrue(all(len(message.to) == 1 for message in mail.outbox))
        member_mail = next(message for message in mail.outbox if message.to == [self.member.email])
        self.assertIn("Bonjour Anis", strip_tags(member_mail.alternatives[0].content))

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


class AudienceTargetingTests(TestCase):
    """Mode B (« Responsables uniquement ») : résolu via effective_role(), jamais une
    liste de rôles recopiée à la main — voir apps.communications.services.broadcast_recipients."""

    def setUp(self):
        self.president = account("president-audience@example.invalid", role=Role.PRESIDENT)
        self.member = account("member-audience@example.invalid", role=Role.MEMBRE)
        self.invite = account("invite-audience@example.invalid", role=Role.INVITE)
        self.gmt = account("gmt-audience@example.invalid", role=Role.GMT)
        self.marketing = account("marketing-audience@example.invalid", role=Role.MARKETING_COMMUNICATION)
        # Deux grants actifs simultanément (le second avec une révocation programmée dans
        # le futur, donc non couvert par l'exclusion DB qui ne porte que sur revoked_at
        # NULL) : rôle effectif ambigu, effective_role() refuse de trancher.
        self.ambiguous = account("ambiguous-audience@example.invalid", role=Role.BUREAU)
        RoleGrant.objects.create(user=self.ambiguous, role=Role.GLT,
            starts_at=timezone.now() - timedelta(hours=1), revoked_at=timezone.now() + timedelta(hours=1))

    def test_ambiguous_role_is_never_resolved(self):
        self.assertIsNone(effective_role(self.ambiguous))

    def test_all_active_includes_every_resolvable_role(self):
        recipients = broadcast_recipients(MemberEmailCampaign.Audience.ALL_ACTIVE)
        self.assertIn(self.president, recipients)
        self.assertIn(self.member, recipients)
        self.assertIn(self.gmt, recipients)
        self.assertIn(self.marketing, recipients)
        self.assertNotIn(self.invite, recipients)
        self.assertNotIn(self.ambiguous, recipients)  # rôle ambigu, jamais ajouté silencieusement

    def test_responsibles_excludes_membre_and_invite_but_keeps_every_other_role(self):
        recipients = broadcast_recipients(MemberEmailCampaign.Audience.RESPONSIBLES)
        self.assertIn(self.president, recipients)
        self.assertIn(self.gmt, recipients)
        self.assertIn(self.marketing, recipients)  # rôle non recopié à la main : suit effective_role()
        self.assertNotIn(self.member, recipients)
        self.assertNotIn(self.invite, recipients)
        self.assertNotIn(self.ambiguous, recipients)


class ExternalEmailsTests(TestCase):
    def setUp(self):
        self.president = account("president-external@example.invalid", role=Role.PRESIDENT)
        self.member = account("member-external@example.invalid", role=Role.MEMBRE)
        self.member_url = reverse("communications:broadcast")

    def post(self, actor, action, **extra):
        self.client.force_login(actor)
        payload = {"subject": "Réunion mensuelle", "body": "Information.", "campaign_key": str(uuid4()),
                   "action": action, "audience": "ALL_ACTIVE", **extra}
        return self.client.post(self.member_url, payload)

    def test_invalid_external_addresses_are_rejected_with_a_clear_error(self):
        response = self.post(self.president, "confirm", extra_emails="abc\ntest@\n@domain.com\nfoo bar")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Adresse")
        self.assertEqual(MemberEmailCampaign.objects.count(), 0)

    def test_more_than_fifty_extra_addresses_is_rejected(self):
        many = ",".join(f"guest{i}@example.invalid" for i in range(51))
        response = self.post(self.president, "confirm", extra_emails=many)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "50 adresses")
        self.assertEqual(MemberEmailCampaign.objects.count(), 0)

    def test_case_insensitive_dedup_collapses_member_and_external_duplicate(self):
        members, external = resolve_broadcast_recipients(
            MemberEmailCampaign.Audience.ALL_ACTIVE, [self.member.email.upper()])
        self.assertIn(self.member, members)
        self.assertEqual(external, [])  # absorbée par le membre interne, jamais un second message

    def test_case_insensitive_dedup_collapses_duplicate_external_addresses(self):
        members, external = resolve_broadcast_recipients(
            MemberEmailCampaign.Audience.ALL_ACTIVE, ["Partenaire@Example.invalid", "partenaire@example.invalid"])
        self.assertEqual(len(external), 1)

    def test_confirmed_send_creates_exactly_one_outbox_message_per_unique_address(self):
        key = str(uuid4())
        self.client.force_login(self.president)
        data = {"subject": "Réunion", "body": "Information.", "campaign_key": key, "action": "send",
                "confirmed": "yes", "audience": "ALL_ACTIVE",
                "extra_emails": f"partenaire@example.invalid, {self.member.email.upper()}, partenaire@example.invalid"}
        response = self.client.post(self.member_url, data)
        self.assertEqual(response.status_code, 302)
        campaign = MemberEmailCampaign.objects.get()
        self.assertEqual(campaign.audience, "ALL_ACTIVE")
        self.assertEqual(campaign.internal_recipient_count, 2)  # président + membre
        self.assertEqual(campaign.external_emails, ["partenaire@example.invalid"])
        self.assertEqual(campaign.recipient_count, 3)  # 2 membres + 1 externe unique
        self.assertEqual(OutboxMessage.objects.filter(kind="MEMBER_BROADCAST").count(), 3)
        self.assertTrue(OutboxMessage.objects.filter(kind="MEMBER_BROADCAST", recipient="partenaire@example.invalid").exists())

    def test_confirm_screen_shows_duplicates_removed_count(self):
        response = self.post(self.president, "confirm", extra_emails=self.member.email.upper())
        self.assertContains(response, "Doublons retirés")
        self.assertContains(response, "<dd>1</dd>", html=True)

    def test_double_submission_with_external_emails_creates_a_single_campaign(self):
        key = str(uuid4())
        self.client.force_login(self.president)
        data = {"subject": "Réunion", "body": "Information.", "campaign_key": key, "action": "send",
                "confirmed": "yes", "audience": "RESPONSIBLES", "extra_emails": "partenaire@example.invalid"}
        first = self.client.post(self.member_url, data)
        second = self.client.post(self.member_url, data)
        third = self.client.post(self.member_url, data)
        self.assertEqual([first.status_code, second.status_code, third.status_code], [302, 302, 302])
        self.assertEqual(MemberEmailCampaign.objects.count(), 1)
        campaign = MemberEmailCampaign.objects.get()
        self.assertEqual(OutboxMessage.objects.filter(kind="MEMBER_BROADCAST").count(), campaign.recipient_count)

    def test_confirm_screen_shows_counts_without_sending(self):
        response = self.post(self.president, "confirm", extra_emails="partenaire@example.invalid")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tous les membres actifs")
        self.assertContains(response, "partenaire@example.invalid")  # visible à l'auteur qui vient de la saisir
        self.assertEqual(MemberEmailCampaign.objects.count(), 0)
        self.assertEqual(OutboxMessage.objects.count(), 0)

    def test_preview_shows_a_second_generic_preview_when_external_addresses_present(self):
        response = self.post(self.president, "preview", extra_emails="partenaire@example.invalid")
        html = response.content.decode()
        self.assertContains(response, "Aperçu pour une adresse externe")
        self.assertEqual(html.count('srcdoc="&lt;!doctype html&gt;'), 2)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_external_address_without_account_gets_generic_greeting(self):
        campaign, created = queue_member_broadcast(
            actor=self.president, subject="Réunion", body="Information.", idempotency_key=uuid4(),
            audience=MemberEmailCampaign.Audience.RESPONSIBLES, extra_emails=["partenaire@example.invalid"],
        )
        self.assertTrue(created)
        report = deliver_batch(limit=10)
        self.assertEqual(report["failed"], 0)
        external_mail = next(m for m in mail.outbox if m.to == ["partenaire@example.invalid"])
        body = strip_tags(external_mail.alternatives[0].content)
        self.assertIn("Bonjour,", body)
        self.assertNotIn("Bonjour ,", body)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_external_address_matching_an_existing_active_user_is_personalized(self):
        self.member.first_name = "Sami"
        self.member.save(update_fields=["first_name"])
        campaign, created = queue_member_broadcast(
            actor=self.president, subject="Réunion", body="Information.", idempotency_key=uuid4(),
            audience=MemberEmailCampaign.Audience.RESPONSIBLES,  # membre exclu de l'audience interne...
            extra_emails=[self.member.email.upper()],  # ...mais ajouté manuellement en externe
        )
        self.assertTrue(created)
        report = deliver_batch(limit=10)
        self.assertEqual(report["failed"], 0)
        # L'adresse envoyée est celle saisie par l'auteur (normalisation de casse
        # réservée à la comparaison/déduplication, pas à la valeur postée) ; la mise en
        # correspondance avec le compte se fait via l'iexact de recipient_for_email().
        member_mail = next(m for m in mail.outbox if m.to == [self.member.email.upper()])
        self.assertIn("Bonjour Sami", strip_tags(member_mail.alternatives[0].content))

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_never_more_than_one_recipient_per_message_no_cc_or_bcc(self):
        queue_member_broadcast(
            actor=self.president, subject="Réunion", body="Information.", idempotency_key=uuid4(),
            audience=MemberEmailCampaign.Audience.ALL_ACTIVE, extra_emails=["partenaire@example.invalid"],
        )
        deliver_batch(limit=10)
        self.assertGreaterEqual(len(mail.outbox), 2)
        for message in mail.outbox:
            self.assertEqual(len(message.to), 1)
            self.assertEqual(message.cc, [])
            self.assertEqual(message.bcc, [])

    def test_history_shows_counts_without_leaking_external_addresses_in_general_list(self):
        queue_member_broadcast(
            actor=self.president, subject="Réunion confidentielle", body="Information.", idempotency_key=uuid4(),
            audience=MemberEmailCampaign.Audience.RESPONSIBLES, extra_emails=["partenaire@example.invalid"],
        )
        self.client.force_login(self.president)
        response = self.client.get(reverse("communications:broadcast_history"))
        self.assertContains(response, "Responsables uniquement")
        self.assertContains(response, "1 externe")
        self.assertNotContains(response, "partenaire@example.invalid")
