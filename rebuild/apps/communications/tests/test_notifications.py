from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from apps.core.tests.test_foundations import account
from apps.governance.models import Role
from ..models import Notification, OutboxMessage
from ..services import notify, send_important_notification


class NotificationTests(TestCase):
    def setUp(self):
        self.member = account("member@example.invalid", role=Role.MEMBRE)
        self.other = account("other@example.invalid", role=Role.MEMBRE)
        self.president = account("president@example.invalid", role=Role.PRESIDENT)
        self.bureau = account("bureau@example.invalid", role=Role.BUREAU)

    def test_notify_is_idempotent_on_event_key(self):
        notify(recipient=self.member, category="EVENT", title="Rappel", event_key="k1")
        notify(recipient=self.member, category="EVENT", title="Rappel", event_key="k1")
        self.assertEqual(Notification.objects.filter(event_key="k1").count(), 1)

    def test_cannot_read_or_mark_read_someone_elses_notification(self):
        notification = notify(recipient=self.other, category="EVENT", title="Privé", event_key="k2")
        self.client.force_login(self.member)
        list_response = self.client.get(reverse("notifications:list"))
        self.assertNotContains(list_response, "Privé")
        mark_response = self.client.post(reverse("notifications:mark_read", args=[notification.pk]))
        self.assertEqual(mark_response.status_code, 404)
        notification.refresh_from_db()
        self.assertIsNone(notification.read_at)

    def test_mark_read_is_post_only(self):
        notification = notify(recipient=self.member, category="EVENT", title="À moi", event_key="k3")
        self.client.force_login(self.member)
        get_response = self.client.get(reverse("notifications:mark_read", args=[notification.pk]))
        self.assertEqual(get_response.status_code, 405)
        notification.refresh_from_db()
        self.assertIsNone(notification.read_at)
        self.client.post(reverse("notifications:mark_read", args=[notification.pk]))
        notification.refresh_from_db()
        self.assertIsNotNone(notification.read_at)

    def test_bureau_cannot_send_important_notification(self):
        with self.assertRaises(PermissionDenied):
            send_important_notification(actor=self.bureau, recipient=self.member, title="x", excerpt="y")

    def test_president_send_creates_notification_and_outbox(self):
        send_important_notification(actor=self.president, recipient=self.member, title="Alerte", excerpt="Détail")
        self.assertTrue(Notification.objects.filter(recipient=self.member, category="IMPORTANT").exists())
        self.assertTrue(OutboxMessage.objects.filter(kind="IMPORTANT", recipient=self.member.email).exists())
