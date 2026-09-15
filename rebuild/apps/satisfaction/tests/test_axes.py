from datetime import timedelta
from django.test import TestCase
from django.core.exceptions import ValidationError, PermissionDenied
from django.urls import reverse
from django.utils import timezone
from apps.core.tests.test_foundations import account
from apps.governance.models import Role
from apps.satisfaction.services import open_period, submit_satisfaction
from apps.satisfaction.selectors import period_results


class AxisTests(TestCase):
    def setUp(self):
        self.president = account("axes-president@example.invalid", role=Role.PRESIDENT)
        self.secretary = account("axes-secretary@example.invalid", role=Role.SECRETAIRE)
        self.member = account("axes-member@example.invalid")
        self.data = dict(year=2026, month=9, threshold=1, opens_at=timezone.now()-timedelta(hours=1), closes_at=timezone.now()+timedelta(days=1), title="Avis", description="Consultation", axes="Organisation\nCommunication")

    def test_managers_create_and_edit_before_responses(self):
        period = open_period(actor=self.president, **self.data)
        self.assertEqual(period.axes.count(), 2)
        data = {**self.data, "axes": "Ambiance\nOrganisation", "title": "Nouveau titre"}
        period = open_period(actor=self.secretary, **data)
        self.assertEqual(list(period.axes.values_list("label", flat=True)), ["Ambiance", "Organisation"])
        for role in (Role.MEMBRE, Role.INVITE):
            actor = account(f"denied-{role}@example.invalid", role=role)
            with self.assertRaises(PermissionDenied):
                open_period(actor=actor, **self.data)
            self.client.force_login(actor)
            self.assertEqual(self.client.get(reverse("satisfaction:edit", args=[period.pk])).status_code, 403)
            self.assertEqual(self.client.post(reverse("satisfaction:edit", args=[period.pk]), {}).status_code, 403)

    def test_structure_locked_and_aggregate_private(self):
        period = open_period(actor=self.secretary, **self.data)
        scores = {axis.pk: 4 for axis in period.axes.all()}
        with self.assertRaises(ValidationError):
            submit_satisfaction(actor=self.member, period=period, score=5)
        submit_satisfaction(actor=self.member, period=period, score=5, axis_scores=scores, comment="Confidentiel")
        with self.assertRaises(ValidationError):
            open_period(actor=self.president, **{**self.data, "axes": "Autre"})
        open_period(actor=self.president, **{**self.data, "title": "Titre corrigé"})
        results = period_results(self.secretary, period)
        self.assertEqual(results["axes"][0]["average"], 4)
        self.assertNotIn("Confidentiel", str(results))
        self.assertNotIn(self.member.email, str(results))
        self.client.force_login(self.secretary)
        response = self.client.get(reverse("satisfaction:results", args=[period.pk]))
        self.assertContains(response, "<meter")
        self.assertNotContains(response, "Confidentiel")
