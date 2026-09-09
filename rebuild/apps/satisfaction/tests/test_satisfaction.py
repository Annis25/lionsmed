from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from zoneinfo import ZoneInfo
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connections, IntegrityError
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from apps.core.tests.test_foundations import account
from apps.core.models import AuditEvent
from apps.governance.models import Role
from .. import services
from ..models import SatisfactionPeriod, SatisfactionResponse
from ..scheduling import third_saturday, compute_window
from ..selectors import period_results

# Heure de référence synthétique pour les tests uniquement ; aucune valeur de production.
SYNTHETIC_HOUR = "00:00"


def force_open_now(period):
    """Ouvre immédiatement une période déjà configurée, pour tester la soumission sans attendre le calendrier réel."""
    SatisfactionPeriod.objects.filter(pk=period.pk).update(
        opens_at=timezone.now() - timedelta(hours=1), closes_at=timezone.now() + timedelta(hours=1))
    period.refresh_from_db()
    return period


class ThirdSaturdayTests(TestCase):
    def test_all_twelve_months_2026(self):
        expected = {1: 17, 2: 21, 3: 21, 4: 18, 5: 16, 6: 20, 7: 18, 8: 15, 9: 19, 10: 17, 11: 21, 12: 19}
        for month, day in expected.items():
            with self.subTest(month=month):
                result = third_saturday(2026, month)
                self.assertEqual(result.weekday(), 5)
                self.assertEqual(result.day, day)

    def test_leap_year_february(self):
        result = third_saturday(2028, 2)  # 2028 est bissextile
        self.assertEqual(result, date(2028, 2, 19))
        self.assertEqual(result.weekday(), 5)

    def test_window_none_when_hour_not_configured(self):
        opens, closes = compute_window(2026, 9)
        self.assertIsNone(opens)
        self.assertIsNone(closes)

    @override_settings(SATISFACTION_REFERENCE_HOUR=SYNTHETIC_HOUR)
    def test_window_configured_africa_tunis(self):
        opens, closes = compute_window(2026, 9)
        self.assertIsNotNone(opens)
        saturday = third_saturday(2026, 9)
        self.assertEqual(timezone.localtime(closes, timezone=ZoneInfo("Africa/Tunis")).date(), date(2026, 9, saturday.day - 1))
        self.assertLess(opens, closes)


class SubmissionTests(TestCase):
    def setUp(self):
        self.president = account("president@example.invalid", role=Role.PRESIDENT)
        self.member = account("member@example.invalid", role=Role.MEMBRE)
        self.invite = account("guest@example.invalid", role=Role.INVITE)

    @override_settings(SATISFACTION_REFERENCE_HOUR=SYNTHETIC_HOUR)
    def test_cannot_open_without_manage_capability(self):
        with self.assertRaises(PermissionDenied):
            services.open_period(actor=self.member, year=2026, month=9)

    def test_open_refused_without_configured_hour(self):
        with self.assertRaises(ValidationError):
            services.open_period(actor=self.president, year=2026, month=9)

    @override_settings(SATISFACTION_REFERENCE_HOUR=SYNTHETIC_HOUR)
    def test_score_out_of_range_refused(self):
        period = force_open_now(services.open_period(actor=self.president, year=2026, month=1))
        with self.assertRaises(ValidationError):
            services.submit_satisfaction(actor=self.member, period=period, score=0)
        with self.assertRaises(ValidationError):
            services.submit_satisfaction(actor=self.member, period=period, score=6)

    @override_settings(SATISFACTION_REFERENCE_HOUR=SYNTHETIC_HOUR)
    def test_invite_cannot_respond(self):
        period = force_open_now(services.open_period(actor=self.president, year=2026, month=1))
        with self.assertRaises(PermissionDenied):
            services.submit_satisfaction(actor=self.invite, period=period, score=4)

    @override_settings(SATISFACTION_REFERENCE_HOUR=SYNTHETIC_HOUR)
    def test_closed_period_refuses_submission(self):
        period = services.open_period(actor=self.president, year=2020, month=1)  # largement passé, jamais forcé ouvert
        with self.assertRaises(ValidationError):
            services.submit_satisfaction(actor=self.member, period=period, score=3)

    @override_settings(SATISFACTION_REFERENCE_HOUR=SYNTHETIC_HOUR)
    def test_single_response_then_refused(self):
        period = force_open_now(services.open_period(actor=self.president, year=2026, month=1))
        services.submit_satisfaction(actor=self.member, period=period, score=5, comment="Très bien")
        with self.assertRaises(ValidationError):
            services.submit_satisfaction(actor=self.member, period=period, score=1)
        self.assertEqual(SatisfactionResponse.objects.filter(period=period).count(), 1)

    @override_settings(SATISFACTION_REFERENCE_HOUR=SYNTHETIC_HOUR)
    def test_audit_never_stores_score_or_comment(self):
        period = force_open_now(services.open_period(actor=self.president, year=2026, month=1))
        services.submit_satisfaction(actor=self.member, period=period, score=2, comment="Commentaire sensible")
        events = AuditEvent.objects.filter(action="satisfaction.responded")
        self.assertTrue(events.exists())
        for field in AuditEvent._meta.get_fields():
            self.assertNotIn("Commentaire sensible", str(getattr(events.first(), field.name, "")))


class ResultsTests(TestCase):
    def setUp(self):
        self.president = account("president@example.invalid", role=Role.PRESIDENT)

    @override_settings(SATISFACTION_REFERENCE_HOUR=SYNTHETIC_HOUR)
    def test_small_cohort_hidden(self):
        period = force_open_now(services.open_period(actor=self.president, year=2026, month=1, threshold=5))
        for i in range(2):
            member = account(f"member{i}@example.invalid", role=Role.MEMBRE)
            services.submit_satisfaction(actor=member, period=period, score=4)
        result = period_results(self.president, period)
        self.assertTrue(result["hidden"])
        self.assertIsNone(result["average"])

    @override_settings(SATISFACTION_REFERENCE_HOUR=SYNTHETIC_HOUR)
    def test_cohort_meeting_threshold_shows_aggregate(self):
        period = force_open_now(services.open_period(actor=self.president, year=2026, month=1, threshold=2))
        for i, score in enumerate([4, 2]):
            member = account(f"member{i}@example.invalid", role=Role.MEMBRE)
            services.submit_satisfaction(actor=member, period=period, score=score)
        result = period_results(self.president, period)
        self.assertFalse(result["hidden"])
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["average"], 3.0)

    def test_member_cannot_view_results(self):
        member = account("member@example.invalid", role=Role.MEMBRE)
        with override_settings(SATISFACTION_REFERENCE_HOUR=SYNTHETIC_HOUR):
            period = services.open_period(actor=self.president, year=2026, month=1)
        self.client.force_login(member)
        self.assertEqual(self.client.get(reverse("satisfaction:results", args=[period.pk])).status_code, 403)


class SatisfactionConcurrencyTests(TransactionTestCase):
    @override_settings(SATISFACTION_REFERENCE_HOUR=SYNTHETIC_HOUR)
    def test_double_post_creates_single_response(self):
        president = account("president@example.invalid", role=Role.PRESIDENT)
        period = force_open_now(services.open_period(actor=president, year=2026, month=1))
        member = account("member@example.invalid", role=Role.MEMBRE)

        def attempt(_):
            try:
                services.submit_satisfaction(actor=member, period=period, score=3)
                return True
            except (ValidationError, IntegrityError):
                return False
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, range(2)))
        self.assertEqual(sum(results), 1)
        self.assertEqual(SatisfactionResponse.objects.filter(period=period).count(), 1)
