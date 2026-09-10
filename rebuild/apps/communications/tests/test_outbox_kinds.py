"""Couverture bout-en-bout de l'outbox pour les types d'e-mail qui n'étaient testés que
côté rendu (voir test_email_campaigns.py) ou pas du tout : rappel de rendez-vous, votes,
satisfaction, et le cas « message devenu non pertinent entre la mise en file et l'envoi »
(_mail_parts() renvoie None), qui ne doit jamais être réessayé inutilement."""
from datetime import timedelta

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.agenda.models import Registration
from apps.agenda.tests.test_agenda import event
from apps.agenda import services as agenda_services
from apps.core.tests.test_foundations import account
from apps.governance.models import Role
from apps.satisfaction import services as satisfaction_services
from apps.satisfaction.notifications import notify_period_opened
from apps.voting.models import Elector, Vote, VoteOption
from apps.voting.notifications import notify_vote_opened, notify_vote_closed

from ..models import OutboxMessage
from ..outbox import deliver_batch


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class EventReminderOutboxTests(TestCase):
    def setUp(self):
        self.president = account("president-reminder@example.invalid", role=Role.PRESIDENT)
        self.member = account("member-reminder@example.invalid", role=Role.MEMBRE)
        self.event = event(self.president, starts_at=timezone.now() + timedelta(days=7), ends_at=timezone.now() + timedelta(days=7, hours=2))
        agenda_services.set_registration(actor=self.member, event=self.event, status=Registration.Status.CONFIRMED)

    def _run_command(self):
        from django.core.management import call_command
        call_command("send_event_reminders")

    def test_confirmed_registrant_gets_reminder_delivered(self):
        self._run_command()
        self.assertTrue(OutboxMessage.objects.filter(kind="EVENT_REMINDER", recipient=self.member.email, state="PENDING").exists())
        report = deliver_batch(limit=5)
        self.assertEqual(report, {"sent": 1, "failed": 0, "disabled": False})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.member.email])
        self.assertIn(self.event.title, mail.outbox[0].subject + mail.outbox[0].alternatives[0].content)

    def test_running_command_twice_does_not_duplicate(self):
        self._run_command()
        self._run_command()
        self.assertEqual(OutboxMessage.objects.filter(kind="EVENT_REMINDER").count(), 1)

    def test_non_registered_member_gets_no_reminder(self):
        other = account("other-reminder@example.invalid", role=Role.MEMBRE)
        self._run_command()
        self.assertFalse(OutboxMessage.objects.filter(kind="EVENT_REMINDER", recipient=other.email).exists())

    def test_vanished_target_is_skipped_without_retry(self):
        """Un événement avec inscriptions confirmées ne peut pas être supprimé (clé
        étrangère PROTECT depuis Registration) : c'est en soi une garde-fou réelle.
        Ce test couvre malgré tout le chemin défensif de _mail_parts() pour une cible
        de notification devenue introuvable (donnée orpheline, réordonnancement...)."""
        import uuid
        from ..models import Notification
        notification = Notification.objects.create(event_key="reminder-orphan", category=Notification.Category.EVENT,
            title="Rappel", recipient=self.member, target_kind="event", target_id=str(uuid.uuid4()))
        item = OutboxMessage.objects.create(event_key="outbox:reminder-orphan", kind="EVENT_REMINDER",
            recipient=self.member.email, object_id=notification.pk)
        report = deliver_batch(limit=5)
        self.assertEqual(report["sent"], 0)
        item.refresh_from_db()
        self.assertEqual(item.state, "FAILED")
        self.assertEqual(item.error_code, "not_applicable")
        self.assertEqual(item.attempts, 1)
        self.assertEqual(len(mail.outbox), 0)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class VoteOutboxTests(TestCase):
    """Construit le scrutin directement (comme test_email_campaigns.py) plutôt que via
    create_and_open_vote/open_vote, qui figent automatiquement TOUS les membres actifs
    comme électeurs — on veut ici contrôler précisément qui est électeur ou non."""

    def setUp(self):
        self.president = account("president-vote-outbox@example.invalid", role=Role.PRESIDENT)
        self.member = account("member-vote-outbox@example.invalid", role=Role.MEMBRE)

    def _open_vote(self, status=Vote.Status.OPEN):
        vote = Vote.objects.create(title="Vote annuel", status=status, mode=Vote.Mode.SINGLE,
            min_choices=1, max_choices=1, opens_at=timezone.now(), responsible=self.president)
        VoteOption.objects.create(vote=vote, label="Oui", order=1)
        VoteOption.objects.create(vote=vote, label="Non", order=2)
        return vote

    def test_vote_opened_delivers_to_electors_only(self):
        vote = self._open_vote()
        Elector.objects.create(vote=vote, profile=self.member.member_profile)
        notify_vote_opened(vote)
        self.assertTrue(OutboxMessage.objects.filter(kind="VOTE_OPENED", recipient=self.member.email).exists())
        self.assertFalse(OutboxMessage.objects.filter(kind="VOTE_OPENED", recipient=self.president.email).exists())
        report = deliver_batch(limit=5)
        self.assertEqual(report, {"sent": 1, "failed": 0, "disabled": False})
        self.assertEqual(mail.outbox[0].to, [self.member.email])

    def test_vote_opened_notification_is_idempotent(self):
        vote = self._open_vote()
        Elector.objects.create(vote=vote, profile=self.member.member_profile)
        notify_vote_opened(vote)
        notify_vote_opened(vote)
        self.assertEqual(OutboxMessage.objects.filter(kind="VOTE_OPENED").count(), 1)

    def test_results_delivered_when_still_authorized(self):
        from apps.voting.models import Ballot, BallotSelection
        vote = self._open_vote(status=Vote.Status.CLOSED)
        elector = Elector.objects.create(vote=vote, profile=self.member.member_profile)
        ballot = Ballot.objects.create(vote=vote)
        BallotSelection.objects.create(ballot=ballot, option=vote.options.get(label="Oui"))
        notify_vote_closed(vote)
        report = deliver_batch(limit=5)
        self.assertEqual(report, {"sent": 1, "failed": 0, "disabled": False})
        html = mail.outbox[0].alternatives[0].content
        self.assertIn("Oui", html)
        self.assertNotIn(str(elector.pk), html)
        self.assertNotIn(str(ballot.pk), html)

    def test_results_not_sent_if_elector_right_revoked_before_delivery_and_not_retried(self):
        vote = self._open_vote(status=Vote.Status.CLOSED)
        elector = Elector.objects.create(vote=vote, profile=self.member.member_profile)
        notify_vote_closed(vote)
        # Le droit de consulter les résultats disparaît avant le passage du worker.
        elector.delete()
        report = deliver_batch(limit=5)
        self.assertEqual(report["sent"], 0)
        item = OutboxMessage.objects.get(kind="VOTE_RESULTS")
        self.assertEqual(item.state, "FAILED")
        self.assertEqual(item.error_code, "not_applicable")
        self.assertEqual(item.attempts, 1)
        self.assertEqual(len(mail.outbox), 0)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SatisfactionOutboxTests(TestCase):
    def setUp(self):
        self.president = account("president-satisfaction-outbox@example.invalid", role=Role.PRESIDENT)
        self.member = account("member-satisfaction-outbox@example.invalid", role=Role.MEMBRE)
        self.invite = account("invite-satisfaction-outbox@example.invalid", role=Role.INVITE)

    def test_eligible_member_gets_email_invite_excluded(self):
        now = timezone.now()
        period = satisfaction_services.open_period(actor=self.president, year=now.year, month=now.month,
            threshold=3, opens_at=now, closes_at=now + timedelta(days=7))
        notify_period_opened(period)
        self.assertTrue(OutboxMessage.objects.filter(kind="SATISFACTION_OPENED", recipient=self.member.email).exists())
        self.assertFalse(OutboxMessage.objects.filter(kind="SATISFACTION_OPENED", recipient=self.invite.email).exists())
        report = deliver_batch(limit=5)
        self.assertEqual(report["failed"], 0)
        self.assertGreaterEqual(report["sent"], 1)

    def test_notify_period_opened_is_idempotent(self):
        now = timezone.now()
        period = satisfaction_services.open_period(actor=self.president, year=now.year, month=now.month,
            threshold=3, opens_at=now, closes_at=now + timedelta(days=7))
        notify_period_opened(period)
        count = OutboxMessage.objects.filter(kind="SATISFACTION_OPENED").count()
        notify_period_opened(period)
        self.assertEqual(OutboxMessage.objects.filter(kind="SATISFACTION_OPENED").count(), count)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class MemberBroadcastSkipTests(TestCase):
    def test_recipient_deactivated_after_queueing_is_skipped_without_retry(self):
        from apps.communications.services import queue_member_broadcast
        from uuid import uuid4
        president = account("president-broadcast-skip@example.invalid", role=Role.PRESIDENT)
        member = account("member-broadcast-skip@example.invalid", role=Role.MEMBRE)
        campaign, created = queue_member_broadcast(actor=president, subject="Info", body="Contenu", idempotency_key=uuid4())
        self.assertTrue(created)
        member.is_active = False
        member.save(update_fields=["is_active"])
        report = deliver_batch(limit=10)
        self.assertEqual(report["sent"], 1)  # le président, toujours actif
        item = OutboxMessage.objects.get(kind="MEMBER_BROADCAST", recipient=member.email)
        self.assertEqual(item.state, "FAILED")
        self.assertEqual(item.error_code, "not_applicable")
        self.assertEqual(item.attempts, 1)
        self.assertEqual(len(mail.outbox), 1)  # seulement le président
        self.assertNotIn(member.email, [message.to[0] for message in mail.outbox])
        campaign.refresh_from_db()
        self.assertEqual(campaign.failed_count, 1)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ActivationSkipTests(TestCase):
    def test_activation_skipped_without_retry_once_password_is_set(self):
        newcomer = account("deja-active@example.invalid", role=Role.MEMBRE)
        item = OutboxMessage.objects.create(event_key=f"activation-skip:{newcomer.pk}", kind="ACTIVATION",
            recipient=newcomer.email, object_id=newcomer.pk)
        newcomer.set_password("Un-mot-de-passe-suffisant-1")
        newcomer.save(update_fields=["password"])
        report = deliver_batch(limit=5)
        self.assertEqual(report["sent"], 0)
        item.refresh_from_db()
        self.assertEqual(item.state, "FAILED")
        self.assertEqual(item.error_code, "not_applicable")
        self.assertEqual(item.attempts, 1)
        self.assertEqual(len(mail.outbox), 0)


class OutboxStatusCommandTests(TestCase):
    def test_reports_counts_without_leaking_recipient_or_content(self):
        import io
        from django.core.management import call_command
        newcomer = account("status-check@example.invalid", role=Role.MEMBRE)
        OutboxMessage.objects.create(event_key="status-pending", kind="ACTIVATION", recipient=newcomer.email, object_id=newcomer.pk)
        OutboxMessage.objects.create(event_key="status-failed", kind="ACTIVATION", recipient=newcomer.email,
            object_id=newcomer.pk, state="FAILED", error_code="delivery_failed")
        out = io.StringIO()
        call_command("outbox_status", stdout=out)
        output = out.getvalue()
        self.assertIn("PENDING: 1", output)
        self.assertIn("FAILED: 1", output)
        self.assertIn("SENT: 0", output)
        self.assertNotIn(newcomer.email, output)

    def test_no_pending_reports_none(self):
        import io
        from django.core.management import call_command
        out = io.StringIO()
        call_command("outbox_status", stdout=out)
        self.assertIn("aucun", out.getvalue())
