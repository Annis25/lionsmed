from datetime import timedelta, datetime, timezone as dt_timezone
from django.test import TestCase
from django.core.exceptions import ValidationError, PermissionDenied
from django.urls import reverse
from django.utils import timezone
from apps.core.tests.test_foundations import account
from apps.governance.models import Role
from apps.satisfaction import services
from apps.satisfaction.selectors import period_results
from apps.satisfaction.models import SatisfactionAxis, SatisfactionPeriod


_month_counter = [0]


def new_period(actor, threshold=1):
    # opens_at fixé à un mois distinct à chaque appel (jamais deux périodes du même
    # mois dans un même test), mais closes_at reste dans le futur : la période est donc
    # « ouverte maintenant » indépendamment du mois qu'elle représente.
    _month_counter[0] += 1
    year, month = divmod(_month_counter[0] - 1, 12)
    opens = datetime(2020 + year, month + 1, 1, tzinfo=dt_timezone.utc)
    return services.create_period(actor=actor, opens_at=opens, closes_at=timezone.now() + timedelta(days=1),
        threshold=threshold, title="Avis", description="Consultation")


class AxisServiceTests(TestCase):
    def setUp(self):
        self.president = account("axes-president@example.invalid", role=Role.PRESIDENT)
        self.secretary = account("axes-secretary@example.invalid", role=Role.SECRETAIRE)
        self.member = account("axes-member@example.invalid")

    def test_managers_add_axes_one_by_one_in_order(self):
        period = new_period(self.president)
        services.add_axis(actor=self.president, period=period, label="Organisation")
        services.add_axis(actor=self.secretary, period=period, label="Communication")
        self.assertEqual(list(period.axes.order_by("order", "pk").values_list("label", flat=True)), ["Organisation", "Communication"])

    def test_period_and_initial_axes_are_created_atomically_in_order(self):
        opens = timezone.now() - timedelta(hours=1)
        period = services.create_period(
            actor=self.secretary,
            opens_at=opens,
            closes_at=timezone.now() + timedelta(days=1),
            threshold=2,
            title="Satisfaction générale",
            axes=["Organisation", "Communication", "Vie du club"],
        )
        self.assertEqual(
            list(period.axes.values_list("label", "order")),
            [("Organisation", 1), ("Communication", 2), ("Vie du club", 3)],
        )

    def test_invalid_initial_axes_do_not_create_a_period(self):
        with self.assertRaises(ValidationError):
            services.create_period(
                actor=self.president,
                opens_at=timezone.now() - timedelta(hours=1),
                closes_at=timezone.now() + timedelta(days=1),
                threshold=1,
                axes=["Organisation", "organisation"],
            )
        self.assertEqual(SatisfactionPeriod.objects.count(), 0)

    def test_non_managers_cannot_touch_axes(self):
        period = new_period(self.president)
        axis = services.add_axis(actor=self.president, period=period, label="Organisation")
        for role in (Role.MEMBRE, Role.INVITE):
            actor = account(f"denied-{role}@example.invalid", role=role)
            with self.assertRaises(PermissionDenied):
                services.add_axis(actor=actor, period=period, label="Autre")
            with self.assertRaises(PermissionDenied):
                services.update_axis(actor=actor, axis=axis, label="Autre")
            with self.assertRaises(PermissionDenied):
                services.delete_axis(actor=actor, axis=axis)
            self.client.force_login(actor)
            self.assertEqual(self.client.get(reverse("satisfaction:edit", args=[period.pk])).status_code, 403)
            self.assertEqual(self.client.post(reverse("satisfaction:axis_add", args=[period.pk]), {"label": "x"}).status_code, 403)

    def test_update_and_delete_axis_before_responses(self):
        period = new_period(self.president)
        axis = services.add_axis(actor=self.president, period=period, label="Organisation")
        services.update_axis(actor=self.secretary, axis=axis, label="Organisation des réunions")
        axis.refresh_from_db()
        self.assertEqual(axis.label, "Organisation des réunions")
        services.delete_axis(actor=self.president, axis=axis)
        self.assertEqual(period.axes.count(), 0)

    def test_duplicate_label_rejected_case_insensitively(self):
        period = new_period(self.president)
        services.add_axis(actor=self.president, period=period, label="Organisation")
        with self.assertRaises(ValidationError):
            services.add_axis(actor=self.president, period=period, label="ORGANISATION")

    def test_blank_label_rejected(self):
        period = new_period(self.president)
        with self.assertRaises(ValidationError):
            services.add_axis(actor=self.president, period=period, label="   ")

    def test_reorder_with_up_and_down(self):
        period = new_period(self.president)
        a = services.add_axis(actor=self.president, period=period, label="A")
        b = services.add_axis(actor=self.president, period=period, label="B")
        c = services.add_axis(actor=self.president, period=period, label="C")
        services.move_axis(actor=self.president, axis=c, direction="up")
        self.assertEqual(list(period.axes.order_by("order", "pk").values_list("label", flat=True)), ["A", "C", "B"])
        services.move_axis(actor=self.president, axis=a, direction="up")  # déjà en tête : sans effet
        self.assertEqual(list(period.axes.order_by("order", "pk").values_list("label", flat=True)), ["A", "C", "B"])

    def test_structure_frozen_after_first_response(self):
        period = new_period(self.president)
        axis = services.add_axis(actor=self.president, period=period, label="Organisation")
        services.submit_satisfaction(actor=self.member, period=period, score=5, axis_scores={axis.pk: 4})
        with self.assertRaises(ValidationError):
            services.add_axis(actor=self.president, period=period, label="Nouveau")
        with self.assertRaises(ValidationError):
            services.update_axis(actor=self.president, axis=axis, label="Renommé")
        with self.assertRaises(ValidationError):
            services.delete_axis(actor=self.president, axis=axis)
        with self.assertRaises(ValidationError):
            services.move_axis(actor=self.president, axis=axis, direction="down")
        axis.refresh_from_db()
        self.assertEqual(axis.label, "Organisation")  # jamais modifié silencieusement

    def test_metadata_frozen_but_title_and_description_editable_after_response(self):
        period = new_period(self.president, threshold=1)
        axis = services.add_axis(actor=self.president, period=period, label="Organisation")
        services.submit_satisfaction(actor=self.member, period=period, score=5, axis_scores={axis.pk: 4})
        with self.assertRaises(ValidationError):
            services.update_period(actor=self.president, period=period, opens_at=period.opens_at + timedelta(hours=1),
                closes_at=period.closes_at, threshold=period.threshold)
        updated = services.update_period(actor=self.president, period=period, opens_at=period.opens_at,
            closes_at=period.closes_at, threshold=period.threshold, title="Titre corrigé", description="Nouvelle description")
        self.assertEqual(updated.title, "Titre corrigé")

    def test_results_stay_aggregate_and_private(self):
        period = new_period(self.president, threshold=1)
        axis = services.add_axis(actor=self.president, period=period, label="Organisation")
        services.submit_satisfaction(actor=self.member, period=period, score=5, axis_scores={axis.pk: 4}, comment="Confidentiel")
        results = period_results(self.secretary, period)
        self.assertEqual(results["axes"][0]["average"], 4)
        self.assertNotIn("Confidentiel", str(results))
        self.assertNotIn(self.member.email, str(results))
        self.client.force_login(self.secretary)
        response = self.client.get(reverse("satisfaction:results", args=[period.pk]))
        self.assertNotContains(response, "Confidentiel")


class AxisViewTests(TestCase):
    def setUp(self):
        self.president = account("axes-view-president@example.invalid", role=Role.PRESIDENT)
        self.period = new_period(self.president)
        self.client.force_login(self.president)

    def test_add_axis_via_view(self):
        response = self.client.post(reverse("satisfaction:axis_add", args=[self.period.pk]), {"label": "Ambiance"})
        self.assertRedirects(response, reverse("satisfaction:edit", args=[self.period.pk]))
        self.assertEqual(self.period.axes.count(), 1)

    def test_edit_axis_via_view(self):
        axis = services.add_axis(actor=self.president, period=self.period, label="Ambiance")
        self.client.post(reverse("satisfaction:axis_edit", args=[self.period.pk, axis.pk]), {"label": "Ambiance générale"})
        axis.refresh_from_db()
        self.assertEqual(axis.label, "Ambiance générale")

    def test_delete_axis_via_view(self):
        axis = services.add_axis(actor=self.president, period=self.period, label="Ambiance")
        self.client.post(reverse("satisfaction:axis_delete", args=[self.period.pk, axis.pk]))
        self.assertFalse(SatisfactionAxis.objects.filter(pk=axis.pk).exists())

    def test_move_axis_via_view(self):
        a = services.add_axis(actor=self.president, period=self.period, label="A")
        b = services.add_axis(actor=self.president, period=self.period, label="B")
        self.client.post(reverse("satisfaction:axis_move", args=[self.period.pk, b.pk]), {"direction": "up"})
        self.assertEqual(list(self.period.axes.order_by("order", "pk").values_list("label", flat=True)), ["B", "A"])

    def test_axis_from_another_period_returns_404(self):
        other_period = new_period(self.president)
        axis = services.add_axis(actor=self.president, period=other_period, label="Ambiance")
        response = self.client.post(reverse("satisfaction:axis_edit", args=[self.period.pk, axis.pk]), {"label": "x"})
        self.assertEqual(response.status_code, 404)

    def test_edit_page_shows_axes_and_freeze_notice_after_response(self):
        axis = services.add_axis(actor=self.president, period=self.period, label="Ambiance")
        response = self.client.get(reverse("satisfaction:edit", args=[self.period.pk]))
        self.assertContains(response, "Ambiance")
        member = account("axes-respondent@example.invalid", role=Role.MEMBRE)
        services.submit_satisfaction(actor=member, period=self.period, score=4, axis_scores={axis.pk: 4})
        response = self.client.get(reverse("satisfaction:edit", args=[self.period.pk]))
        self.assertContains(response, "figé")
