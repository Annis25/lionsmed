from datetime import timedelta
from uuid import uuid4
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.core import mail
from django.urls import reverse
from django.utils import timezone
from apps.core.tests.test_foundations import account
from apps.governance.models import Role
from apps.communications.models import OutboxMessage
from apps.communications.outbox import deliver_batch
from apps.agenda.services import create_calendar_event, notify_event_created
from apps.agenda.models import Event


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class CreatedEmailTests(TestCase):
    def setUp(self):
        self.actor = account("created-president@example.invalid", role=Role.PRESIDENT)
        self.member = account("created-member@example.invalid")
        self.guest = account("created-guest@example.invalid", role=Role.INVITE)
        self.inactive = account("created-inactive@example.invalid", is_active=False)
        self.now = timezone.now()

    def create(self, days, key=None):
        with patch("apps.agenda.services.timezone.now", return_value=self.now):
            return create_calendar_event(actor=self.actor, title="Événement synthétique", description="Résumé", starts_at=self.now+timedelta(days=days), ends_at=self.now+timedelta(days=days, hours=1), all_day=False, location="Club", meeting_link="", creation_key=key)

    def test_boundaries_recipients_and_replay(self):
        for days in (2, 6, 7, 8, -1):
            with self.subTest(days=days):
                OutboxMessage.objects.all().delete()
                key = uuid4()
                event = self.create(days, key)
                replay = self.create(days, key)
                self.assertEqual(event.pk, replay.pk)
                expected = 2 if days in (2, 6, 7) else 0
                self.assertEqual(OutboxMessage.objects.filter(kind="EVENT_CREATED").count(), expected)
                self.assertFalse(OutboxMessage.objects.filter(recipient=self.guest.email).exists())
                self.assertFalse(OutboxMessage.objects.filter(recipient=self.inactive.email).exists())

    def test_delivered_once_and_removed_permission_not_applicable(self):
        event = self.create(2, uuid4())
        notify_event_created(event)
        self.assertEqual(OutboxMessage.objects.count(), 2)
        report = deliver_batch(limit=10)
        self.assertEqual(report["sent"], 2)
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("nouvel événement", mail.outbox[0].body.lower())
        self.assertFalse(OutboxMessage.objects.exclude(state="SENT").exists())

    def test_http_double_post_and_missing_key(self):
        self.client.force_login(self.actor)
        key = self.client.get(reverse("agenda_private:calendar")).context["quick_form"].initial["creation_key"]
        data = {"creation_key": str(key), "title": "HTTP unique", "starts_at": (self.now+timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"), "location": "Club"}
        for _ in range(2):
            self.assertEqual(self.client.post(reverse("agenda_private:calendar_event_add"), data).status_code, 302)
        self.assertEqual(Event.objects.filter(title="HTTP unique").count(), 1)
        self.assertEqual(OutboxMessage.objects.count(), 2)
