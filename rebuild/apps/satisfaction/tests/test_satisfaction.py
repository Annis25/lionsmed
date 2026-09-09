from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta, datetime, time
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
from ..scheduling import second_friday, third_friday, compute_auto_window
from ..selectors import period_results

# Heure de référence synthétique pour les tests uniquement ; aucune valeur de production.
SYNTHETIC_HOUR = "00:00"
DEFAULT_THRESHOLD = 5


def force_open_now(period):
    """Ouvre immédiatement une période déjà configurée, pour tester la soumission sans attendre le calendrier réel."""
    SatisfactionPeriod.objects.filter(pk=period.pk).update(
        opens_at=timezone.now() - timedelta(hours=1), closes_at=timezone.now() + timedelta(hours=1))
    period.refresh_from_db()
    return period


def open_auto(actor, year, month, threshold=DEFAULT_THRESHOLD):
    return services.open_period(actor=actor, year=year, month=month, threshold=threshold, auto_schedule=True)


def open_manual(actor, year, month, opens_at, closes_at, threshold=DEFAULT_THRESHOLD):
    return services.open_period(actor=actor, year=year, month=month, threshold=threshold,
        auto_schedule=False, opens_at=opens_at, closes_at=closes_at)


class SchedulingTests(TestCase):
    def test_all_twelve_months_2026_second_and_third_friday(self):
        expected_second = {1: 9, 2: 13, 3: 13, 4: 10, 5: 8, 6: 12, 7: 10, 8: 14, 9: 11, 10: 9, 11: 13, 12: 11}
        for month, day in expected_second.items():
            with self.subTest(month=month):
                second = second_friday(2026, month)
                third = third_friday(2026, month)
                self.assertEqual(second.weekday(), 4)
                self.assertEqual(third.weekday(), 4)
                self.assertEqual(second.day, day)
                self.assertEqual(third.day, day + 7)

    def test_leap_year_february(self):
        second = second_friday(2028, 2)
        self.assertEqual(second, date(2028, 2, 11))
        self.assertEqual(second.weekday(), 4)

    def test_window_none_when_hour_not_configured(self):
        opens, closes = compute_auto_window(2026, 9)
        self.assertIsNone(opens)
        self.assertIsNone(closes)

    @override_settings(SATISFACTION_REFERENCE_HOUR=SYNTHETIC_HOUR)
    def test_window_configured_africa_tunis_second_to_third_friday(self):
        opens, closes = compute_auto_window(2026, 9)
        self.assertIsNotNone(opens)
        third = third_friday(2026, 9)
        self.assertEqual(timezone.localtime(closes, timezone=ZoneInfo("Africa/Tunis")).date(), third)
        self.assertLess(opens, closes)


class SubmissionTests(TestCase):
    def setUp(self):
        self.president = account("president@example.invalid", role=Role.PRESIDENT)
        self.member = account("member@example.invalid", role=Role.MEMBRE)
        self.invite = account("guest@example.invalid", role=Role.INVITE)

    @override_settings(SATISFACTION_REFERENCE_HOUR=SYNTHETIC_HOUR)
    def test_cannot_open_without_manage_capability(self):
        with self.assertRaises(PermissionDenied):
            open_auto(self.member, 2026, 9)

    def test_auto_open_refused_without_configured_hour(self):
        with self.assertRaises(ValidationError):
            open_auto(self.president, 2026, 9)

    def test_manual_open_requires_both_dates(self):
        with self.assertRaises(ValidationError):
            services.open_period(actor=self.president, year=2026, month=9, threshold=DEFAULT_THRESHOLD, auto_schedule=False)

    def test_manual_open_rejects_close_before_open(self):
        now = timezone.now()
        with self.assertRaises(ValidationError):
            open_manual(self.president, 2026, 9, now, now - timedelta(hours=1))

    def test_manual_open_with_explicit_dates(self):
        opens = timezone.now() - timedelta(hours=1)
        closes = timezone.now() + timedelta(days=1)
        period = open_manual(self.president, 2026, 9, opens, closes)
        self.assertEqual(period.opens_at, opens)
        self.assertEqual(period.closes_at, closes)

    @override_settings(SATISFACTION_REFERENCE_HOUR=SYNTHETIC_HOUR)
    def test_score_out_of_range_refused(self):
        period = force_open_now(open_auto(self.president, 2026, 1))
        with self.assertRaises(ValidationError):
            services.submit_satisfaction(actor=self.member, period=period, score=0)
        with self.assertRaises(ValidationError):
            services.submit_satisfaction(actor=self.member, period=period, score=6)

    @override_settings(SATISFACTION_REFERENCE_HOUR=SYNTHETIC_HOUR)
    def test_invite_cannot_respond(self):
        period = force_open_now(open_auto(self.president, 2026, 1))
        with self.assertRaises(PermissionDenied):
            services.submit_satisfaction(actor=self.invite, period=period, score=4)

    @override_settings(SATISFACTION_REFERENCE_HOUR=SYNTHETIC_HOUR)
    def test_closed_period_refuses_submission(self):
        period = open_auto(self.president, 2020, 1)  # largement passé, jamais forcé ouvert
        with self.assertRaises(ValidationError):
            services.submit_satisfaction(actor=self.member, period=period, score=3)

    @override_settings(SATISFACTION_REFERENCE_HOUR=SYNTHETIC_HOUR)
    def test_single_response_then_refused(self):
        period = force_open_now(open_auto(self.president, 2026, 1))
        services.submit_satisfaction(actor=self.member, period=period, score=5, comment="Très bien")
        with self.assertRaises(ValidationError):
            services.submit_satisfaction(actor=self.member, period=period, score=1)
        self.assertEqual(SatisfactionResponse.objects.filter(period=period).count(), 1)

    @override_settings(SATISFACTION_REFERENCE_HOUR=SYNTHETIC_HOUR)
    def test_audit_never_stores_score_or_comment(self):
        period = force_open_now(open_auto(self.president, 2026, 1))
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
        period = force_open_now(open_auto(self.president, 2026, 1, threshold=5))
        for i in range(2):
            member = account(f"member{i}@example.invalid", role=Role.MEMBRE)
            services.submit_satisfaction(actor=member, period=period, score=4)
        result = period_results(self.president, period)
        self.assertTrue(result["hidden"])
        self.assertIsNone(result["average"])

    @override_settings(SATISFACTION_REFERENCE_HOUR=SYNTHETIC_HOUR)
    def test_cohort_meeting_threshold_shows_aggregate(self):
        period = force_open_now(open_auto(self.president, 2026, 1, threshold=2))
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
            period = open_auto(self.president, 2026, 1)
        self.client.force_login(member)
        self.assertEqual(self.client.get(reverse("satisfaction:results", args=[period.pk])).status_code, 403)


class SatisfactionConcurrencyTests(TransactionTestCase):
    @override_settings(SATISFACTION_REFERENCE_HOUR=SYNTHETIC_HOUR)
    def test_double_post_creates_single_response(self):
        president = account("president@example.invalid", role=Role.PRESIDENT)
        period = force_open_now(open_auto(president, 2026, 1))
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


class ManageViewAndNavigationTests(TestCase):
    def setUp(self):
        self.president = account("president2@example.invalid", role=Role.PRESIDENT)
        self.member = account("member2@example.invalid", role=Role.MEMBRE)

    def test_manager_sees_satisfaction_as_expandable_group(self):
        self.client.force_login(self.president)
        response = self.client.get(reverse("core:dashboard"))
        nav = {item["label"]: item for item in response.context["private_navigation"]}
        self.assertIn("children", nav["Satisfaction"])
        self.assertEqual({c["label"] for c in nav["Satisfaction"]["children"]}, {"Répondre", "Gestion"})

    def test_plain_member_sees_satisfaction_as_flat_link(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("core:dashboard"))
        nav = {item["label"]: item for item in response.context["private_navigation"]}
        self.assertNotIn("children", nav["Satisfaction"])
        self.assertEqual(nav["Satisfaction"]["url"], reverse("satisfaction:respond"))

    def test_manage_view_opens_period_with_manual_dates(self):
        self.client.force_login(self.president)
        opens = timezone.now() + timedelta(days=1)
        closes = timezone.now() + timedelta(days=10)
        response = self.client.post(reverse("satisfaction:manage_list"), {
            "year": "2027", "month": "3", "threshold": "3",
            "opens_at": opens.strftime("%Y-%m-%dT%H:%M"), "closes_at": closes.strftime("%Y-%m-%dT%H:%M"),
        })
        self.assertRedirects(response, reverse("satisfaction:manage_list"))
        period = SatisfactionPeriod.objects.get(month=date(2027, 3, 1))
        self.assertEqual(period.threshold, 3)
        self.assertIsNotNone(period.opens_at)

    @override_settings(SATISFACTION_REFERENCE_HOUR=SYNTHETIC_HOUR)
    def test_manage_view_auto_schedule_uses_second_and_third_friday(self):
        self.client.force_login(self.president)
        response = self.client.post(reverse("satisfaction:manage_list"), {
            "year": "2026", "month": "9", "threshold": "5", "auto_schedule": "on",
        })
        self.assertRedirects(response, reverse("satisfaction:manage_list"))
        period = SatisfactionPeriod.objects.get(month=date(2026, 9, 1))
        self.assertEqual(timezone.localtime(period.opens_at, ZoneInfo("Africa/Tunis")).date(), second_friday(2026, 9))
        self.assertEqual(timezone.localtime(period.closes_at, ZoneInfo("Africa/Tunis")).date(), third_friday(2026, 9))

    def test_manage_view_rejects_missing_dates_without_auto(self):
        self.client.force_login(self.president)
        response = self.client.post(reverse("satisfaction:manage_list"), {
            "year": "2026", "month": "9", "threshold": "5",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SatisfactionPeriod.objects.filter(month=date(2026, 9, 1)).exists())
