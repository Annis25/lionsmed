from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connections, IntegrityError
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from apps.core.tests.test_foundations import account
from apps.core.models import AuditEvent
from apps.governance.models import Role
from .. import services
from ..models import SatisfactionPeriod, SatisfactionResponse
from ..selectors import period_results, own_response

DEFAULT_THRESHOLD = 5


def force_open_now(period):
    """Ouvre immédiatement une période déjà configurée, pour tester la soumission sans attendre le calendrier réel."""
    SatisfactionPeriod.objects.filter(pk=period.pk).update(
        opens_at=timezone.now() - timedelta(hours=1), closes_at=timezone.now() + timedelta(hours=1))
    period.refresh_from_db()
    return period


def open_period(actor, opens_at=None, closes_at=None, threshold=DEFAULT_THRESHOLD, **extra):
    opens_at = opens_at or (timezone.now() - timedelta(hours=1))
    closes_at = closes_at or (timezone.now() + timedelta(days=1))
    return services.create_period(actor=actor, opens_at=opens_at, closes_at=closes_at, threshold=threshold, **extra)


class SubmissionTests(TestCase):
    def setUp(self):
        self.president = account("president@example.invalid", role=Role.PRESIDENT)
        self.member = account("member@example.invalid", role=Role.MEMBRE)
        self.invite = account("guest@example.invalid", role=Role.INVITE)

    def test_cannot_open_without_manage_capability(self):
        with self.assertRaises(PermissionDenied):
            open_period(self.member)

    def test_create_requires_both_dates(self):
        with self.assertRaises(ValidationError):
            services.create_period(actor=self.president, opens_at=None, closes_at=None, threshold=DEFAULT_THRESHOLD)

    def test_create_rejects_close_before_open(self):
        now = timezone.now()
        with self.assertRaises(ValidationError):
            open_period(self.president, opens_at=now, closes_at=now - timedelta(hours=1))

    def test_create_derives_month_from_opens_at(self):
        opens = timezone.now().replace(year=2026, month=9, day=20, hour=10, minute=0, second=0, microsecond=0)
        closes = opens + timedelta(days=1)
        period = open_period(self.president, opens_at=opens, closes_at=closes)
        self.assertEqual(period.month.year, 2026)
        self.assertEqual(period.month.month, 9)
        self.assertEqual(period.month.day, 1)

    def test_several_periods_in_the_same_month_are_allowed(self):
        # `month` n'est plus qu'un libellé dérivé de opens_at : plus aucune contrainte
        # d'unicité n'empêche deux consultations sur le même mois calendaire.
        opens = timezone.now().replace(year=2026, month=9, day=5, hour=10, minute=0, second=0, microsecond=0)
        closes = opens + timedelta(hours=2)
        first = open_period(self.president, opens_at=opens, closes_at=closes, title="Première")
        second = open_period(self.president, opens_at=opens + timedelta(days=10), closes_at=closes + timedelta(days=10), title="Seconde")
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(first.month, second.month)
        self.assertEqual(SatisfactionPeriod.objects.filter(month=first.month).count(), 2)

    def test_score_out_of_range_refused(self):
        period = force_open_now(open_period(self.president))
        with self.assertRaises(ValidationError):
            services.submit_satisfaction(actor=self.member, period=period, score=0)
        with self.assertRaises(ValidationError):
            services.submit_satisfaction(actor=self.member, period=period, score=6)

    def test_invite_cannot_respond(self):
        period = force_open_now(open_period(self.president))
        with self.assertRaises(PermissionDenied):
            services.submit_satisfaction(actor=self.invite, period=period, score=4)

    def test_closed_period_refuses_submission(self):
        past = timezone.now() - timedelta(days=400)
        period = open_period(self.president, opens_at=past, closes_at=past + timedelta(days=1))  # jamais forcé ouvert
        with self.assertRaises(ValidationError):
            services.submit_satisfaction(actor=self.member, period=period, score=3)

    def test_single_response_then_refused(self):
        period = force_open_now(open_period(self.president))
        services.submit_satisfaction(actor=self.member, period=period, score=5, comment="Très bien")
        with self.assertRaises(ValidationError):
            services.submit_satisfaction(actor=self.member, period=period, score=1)
        self.assertEqual(SatisfactionResponse.objects.filter(period=period).count(), 1)

    def test_comment_over_500_chars_is_truncated_not_rejected(self):
        period = force_open_now(open_period(self.president))
        long_comment = "x" * 600
        response = services.submit_satisfaction(actor=self.member, period=period, score=3, comment=long_comment)
        self.assertEqual(len(response.comment), 500)

    def test_audit_never_stores_score_or_comment(self):
        period = force_open_now(open_period(self.president))
        services.submit_satisfaction(actor=self.member, period=period, score=2, comment="Commentaire sensible")
        events = AuditEvent.objects.filter(action="satisfaction.responded")
        self.assertTrue(events.exists())
        for field in AuditEvent._meta.get_fields():
            self.assertNotIn("Commentaire sensible", str(getattr(events.first(), field.name, "")))

    def test_axis_questions_are_numbered_sequentially_after_the_main_score(self):
        # Régression : le gabarit numérote chaque question par sa position dans le
        # formulaire (score=1, puis les axes) ; « comment » doit rester hors du calcul
        # quel que soit son rang dans self.fields (voir SatisfactionForm.__init__).
        period = force_open_now(open_period(self.president))
        services.add_axis(actor=self.president, period=period, label="Organisation")
        services.add_axis(actor=self.president, period=period, label="Communication")
        self.client.force_login(self.member)
        html = self.client.get(reverse("satisfaction:respond")).content.decode()
        for number, label in [(1, "Comment évaluez-vous ce mois au club ?"), (2, "Organisation"), (3, "Communication")]:
            needle = f'<span class="smiley-scale__number" aria-hidden="true">{number}</span><span class="smiley-scale__label">{label}</span>'
            self.assertIn(needle, html)

    def test_two_periods_open_at_once_both_appear_and_are_answered_independently(self):
        # open_period() par défaut ouvre déjà "maintenant" (now-1h -> now+1j) : les deux
        # appels tombent dans le même mois calendaire, ce qui est précisément le cas que
        # la levée de la contrainte d'unicité doit désormais permettre.
        first = open_period(self.president, title="Premier sondage")
        second = open_period(self.president, title="Autre sondage")
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(first.month, second.month)
        self.client.force_login(self.member)

        html = self.client.get(reverse("satisfaction:respond")).content.decode()
        self.assertEqual(html.count('name="period_id"'), 2)
        self.assertIn(f'value="{first.pk}"', html)
        self.assertIn(f'value="{second.pk}"', html)

        # Répondre à "second" ne doit ni répondre à "first" ni le faire disparaître.
        data = {"period_id": str(second.pk), f"{second.pk}-score": "4"}
        response = self.client.post(reverse("satisfaction:respond"), data)
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(own_response(self.member, second))
        self.assertIsNone(own_response(self.member, first))

        html = self.client.get(reverse("satisfaction:respond")).content.decode()
        self.assertIn("Merci, votre avis a déjà été enregistré", html)  # pour "second"
        self.assertIn(f'name="{first.pk}-score"', html)  # "first" toujours à répondre


class ResultsTests(TestCase):
    def setUp(self):
        self.president = account("president@example.invalid", role=Role.PRESIDENT)

    def test_small_cohort_hidden(self):
        period = force_open_now(open_period(self.president, threshold=5))
        for i in range(2):
            member = account(f"member{i}@example.invalid", role=Role.MEMBRE)
            services.submit_satisfaction(actor=member, period=period, score=4)
        result = period_results(self.president, period)
        self.assertTrue(result["hidden"])
        self.assertIsNone(result["average"])
        self.assertIsNone(result["participation_rate"])

    def test_cohort_meeting_threshold_shows_aggregate_and_participation_rate(self):
        period = force_open_now(open_period(self.president, threshold=2))
        for i, score in enumerate([4, 2]):
            member = account(f"member{i}@example.invalid", role=Role.MEMBRE)
            services.submit_satisfaction(actor=member, period=period, score=score)
        result = period_results(self.president, period)
        self.assertFalse(result["hidden"])
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["average"], 3.0)
        self.assertIsNotNone(result["participation_rate"])
        self.assertGreater(result["eligible_count"], 0)

    def test_member_cannot_view_results(self):
        member = account("member@example.invalid", role=Role.MEMBRE)
        period = open_period(self.president)
        self.client.force_login(member)
        self.assertEqual(self.client.get(reverse("satisfaction:results", args=[period.pk])).status_code, 403)


class SatisfactionConcurrencyTests(TransactionTestCase):
    def test_double_post_creates_single_response(self):
        president = account("president@example.invalid", role=Role.PRESIDENT)
        period = force_open_now(open_period(president))
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

    def test_manage_view_creates_period_with_manual_dates_no_year_or_month_field(self):
        self.client.force_login(self.president)
        opens = timezone.now() + timedelta(days=1)
        closes = timezone.now() + timedelta(days=10)
        response = self.client.post(reverse("satisfaction:manage_list"), {
            "threshold": "3",
            "opens_at": opens.strftime("%Y-%m-%dT%H:%M"), "closes_at": closes.strftime("%Y-%m-%dT%H:%M"),
            "axes": "Organisation\nCommunication",
        })
        period = SatisfactionPeriod.objects.get()
        self.assertRedirects(response, reverse("satisfaction:edit", args=[period.pk]))
        self.assertEqual(period.threshold, 3)
        self.assertEqual(list(period.axes.values_list("label", flat=True)), ["Organisation", "Communication"])
        self.assertIsNotNone(period.opens_at)
        form_page = self.client.get(reverse("satisfaction:manage_list"))
        self.assertNotContains(form_page, 'name="year"')
        self.assertNotContains(form_page, 'name="month"')
        self.assertNotContains(form_page, 'name="auto_schedule"')

    def test_manage_view_rejects_missing_dates(self):
        self.client.force_login(self.president)
        response = self.client.post(reverse("satisfaction:manage_list"), {"threshold": "5", "axes": "Organisation"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SatisfactionPeriod.objects.count(), 0)

    def test_manage_view_requires_initial_axes_and_preserves_the_form(self):
        self.client.force_login(self.president)
        now = timezone.now()
        response = self.client.post(reverse("satisfaction:manage_list"), {
            "title": "Satisfaction générale",
            "threshold": "2",
            "opens_at": now.strftime("%Y-%m-%dT%H:%M"),
            "closes_at": (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
            "axes": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ce champ est obligatoire.", count=1)
        self.assertContains(response, "Satisfaction générale")
        self.assertEqual(SatisfactionPeriod.objects.count(), 0)

    def test_manage_view_rejects_duplicate_initial_axes_without_partial_creation(self):
        self.client.force_login(self.president)
        now = timezone.now()
        response = self.client.post(reverse("satisfaction:manage_list"), {
            "threshold": "2",
            "opens_at": now.strftime("%Y-%m-%dT%H:%M"),
            "closes_at": (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
            "axes": "Organisation\nORGANISATION",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Chaque axe doit avoir un nom différent.", count=1)
        self.assertEqual(SatisfactionPeriod.objects.count(), 0)

    def test_gestion_non_field_error_shown_once_in_a_compact_alert(self):
        # Erreur croisée (clean()), non rattachée à un champ précis : plus de gros
        # bloc récapitulatif dupliqué — une alerte compacte, une seule fois.
        self.client.force_login(self.president)
        now = timezone.now()
        response = self.client.post(reverse("satisfaction:manage_list"), {
            "threshold": "1",
            "opens_at": now.strftime("%Y-%m-%dT%H:%M"),
            "closes_at": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
            "axes": "Organisation",
        })
        html = response.content.decode()
        self.assertNotIn("Vérifiez les informations du formulaire", html)
        self.assertIn("form-errors--compact", html)
        self.assertEqual(html.count("La fermeture doit être postérieure au lancement."), 1)

    def test_gestion_field_error_shown_once_under_its_field(self):
        self.client.force_login(self.president)
        now = timezone.now()
        response = self.client.post(reverse("satisfaction:manage_list"), {
            "threshold": "",
            "opens_at": now.strftime("%Y-%m-%dT%H:%M"),
            "closes_at": (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
            "axes": "Organisation",
        })
        html = response.content.decode()
        self.assertNotIn("Vérifiez les informations du formulaire", html)
        self.assertEqual(html.count("Ce champ est obligatoire."), 1)

    def test_gestion_and_edit_headings_are_compact_single_line(self):
        self.client.force_login(self.president)
        gestion_html = self.client.get(reverse("satisfaction:manage_list")).content.decode()
        self.assertIn("<h1>Satisfaction</h1>", gestion_html)
        period = open_period(self.president)
        edit_html = self.client.get(reverse("satisfaction:edit", args=[period.pk])).content.decode()
        self.assertIn("<h1>Modifier</h1>", edit_html)

    def test_respond_page_radios_stay_real_focusable_inputs(self):
        # Masqués visuellement (CSS clip, voir .smiley-option input), jamais retirés du
        # DOM ni transformés en type="hidden" : le clavier et les lecteurs d'écran
        # doivent continuer à les voir comme de vrais boutons radio.
        period = force_open_now(open_period(self.president))
        self.client.force_login(self.member)
        html = self.client.get(reverse("satisfaction:respond")).content.decode()
        self.assertIn('type="radio"', html)
        self.assertNotIn('type="hidden" name="score"', html)
        self.assertGreaterEqual(html.count('type="radio"'), 5)
