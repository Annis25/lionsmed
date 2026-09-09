from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connections, IntegrityError
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from apps.core.tests.test_foundations import account
from apps.core.permissions import can
from apps.governance.models import Role
from apps.editorial.publication import publish_content
from .. import services
from ..models import Event, Registration, Attendance
from ..selectors import upcoming_events, own_registration


def event(actor, **kwargs):
    data = dict(title="Réunion synthétique", slug="reunion-"+str(timezone.now().timestamp()).replace(".", ""),
        summary="Résumé", body="Récit", created_by=actor, updated_by=actor,
        starts_at=timezone.now()+timedelta(days=3), ends_at=timezone.now()+timedelta(days=3, hours=2),
        location="Local du club", visibility="PRIVATE", registration_enabled=True)
    data.update(kwargs)
    obj = Event.objects.create(**data)
    return publish_content(actor=actor, obj=obj, kind="event")


class RegistrationTests(TestCase):
    def setUp(self):
        self.president = account("president@example.invalid", role=Role.PRESIDENT)
        self.member = account("member@example.invalid", role=Role.MEMBRE)
        self.invite = account("guest@example.invalid", role=Role.INVITE)
        self.event = event(self.president)

    def test_private_event_visible_in_member_calendar(self):
        self.assertIn(self.event, list(upcoming_events(self.member)))

    def test_invite_cannot_register(self):
        with self.assertRaises(PermissionDenied):
            services.set_registration(actor=self.invite, event=self.event, status=Registration.Status.CONFIRMED)
        self.assertFalse(can(self.invite, "event.register"))

    def test_confirm_then_cancel_round_trip(self):
        registration = services.set_registration(actor=self.member, event=self.event, status=Registration.Status.CONFIRMED)
        self.assertEqual(registration.status, Registration.Status.CONFIRMED)
        self.assertEqual(own_registration(self.member, self.event).status, Registration.Status.CONFIRMED)
        services.set_registration(actor=self.member, event=self.event, status=Registration.Status.CANCELLED)
        self.assertEqual(own_registration(self.member, self.event).status, Registration.Status.CANCELLED)

    def test_registration_requires_registration_enabled(self):
        closed = event(self.president, slug="ferme", registration_enabled=False)
        with self.assertRaises(ValidationError):
            services.set_registration(actor=self.member, event=closed, status=Registration.Status.CONFIRMED)

    def test_rsvp_view_is_scoped_to_own_profile(self):
        other = account("other-member@example.invalid", role=Role.MEMBRE)
        self.client.force_login(self.member)
        self.client.post(reverse("agenda_private:rsvp", args=[self.event.pk]), {"action": "confirm"})
        self.client.force_login(other)
        self.client.post(reverse("agenda_private:rsvp", args=[self.event.pk]), {"action": "confirm"})
        self.assertEqual(own_registration(self.member, self.event).status, Registration.Status.CONFIRMED)
        self.assertEqual(own_registration(other, self.event).status, Registration.Status.CONFIRMED)
        self.assertEqual(Registration.objects.filter(event=self.event).count(), 2)

    def test_rsvp_confirmation_does_not_create_attendance(self):
        """RSVP != présence : confirmer une inscription ne renseigne jamais Attendance."""
        services.set_registration(actor=self.member, event=self.event, status=Registration.Status.CONFIRMED)
        self.assertFalse(Attendance.objects.filter(event=self.event, profile=self.member.member_profile).exists())


class AttendanceTests(TestCase):
    def setUp(self):
        self.president = account("president@example.invalid", role=Role.PRESIDENT)
        self.member = account("member@example.invalid", role=Role.MEMBRE)
        self.bureau = account("bureau@example.invalid", role=Role.BUREAU)
        self.event = event(self.president)

    def test_bureau_cannot_record_attendance(self):
        with self.assertRaises(PermissionDenied):
            services.record_attendance(actor=self.bureau, event=self.event, profile=self.member.member_profile, status="PRESENT")

    def test_president_records_attendance(self):
        attendance = services.record_attendance(actor=self.president, event=self.event, profile=self.member.member_profile, status="EXCUSED", note="Voyage")
        self.assertEqual(attendance.status, "EXCUSED")
        self.assertEqual(attendance.recorded_by, self.president)

    def test_missing_row_is_not_recorded_absent(self):
        """Absence de ligne Attendance = non renseigné, jamais ABSENT implicite."""
        self.assertIsNone(Attendance.objects.filter(event=self.event, profile=self.member.member_profile).first())

    def test_attendance_view_requires_capability(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("agenda_private:attendance_sheet", args=[self.event.pk]))
        self.assertEqual(response.status_code, 403)


class CapacityConcurrencyTests(TransactionTestCase):
    def test_last_seat_is_awarded_exactly_once(self):
        president = account("president@example.invalid", role=Role.PRESIDENT)
        rendezvous = event(president, slug="capacite", capacity=1)
        first = account("first@example.invalid", role=Role.MEMBRE)
        second = account("second@example.invalid", role=Role.MEMBRE)

        def attempt(user):
            try:
                services.set_registration(actor=user, event=rendezvous, status=Registration.Status.CONFIRMED)
                return True
            except ValidationError:
                return False
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, [first, second]))
        self.assertEqual(sum(results), 1)
        self.assertEqual(Registration.objects.filter(event=rendezvous, status=Registration.Status.CONFIRMED).count(), 1)
