from uuid import uuid4

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from apps.core.permissions import can
from apps.core.tests.test_foundations import account
from apps.governance.models import Role
from apps.members.models import MemberProfile
from apps.voting.models import Vote, VoteOption, Elector, Ballot, BallotSelection
from apps.voting.selectors import vote_results

from ..emailing import render_transactional
from ..models import MemberEmailCampaign, OutboxMessage
from ..outbox import deliver_batch


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
                   "campaign_key": str(uuid4()), "action": action, **extra}
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
                "action": "send", "confirmed": "yes"}
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
            "action": "send", "confirmed": "yes",
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
