from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from apps.core.tests.test_foundations import account
from apps.governance.models import Role, LionsYear
from .. import services
from ..models import DuesRecord


def lions_year():
    today = timezone.localdate()
    return LionsYear.objects.create(starts_on=today.replace(month=7, day=1), ends_on=today.replace(year=today.year+1, month=7, day=1))


class DuesTests(TestCase):
    def setUp(self):
        self.president = account("president@example.invalid", role=Role.PRESIDENT)
        self.member = account("member@example.invalid", role=Role.MEMBRE)
        self.other = account("other@example.invalid", role=Role.MEMBRE)
        self.year = lions_year()
        self.record = services.ensure_record(actor=self.president, profile=self.member.member_profile, lions_year=self.year)

    def test_member_cannot_manage_dues(self):
        with self.assertRaises(PermissionDenied):
            services.record_dues_status(actor=self.member, record=self.record, status="PAID", amount=None, paid_on=None, motif="tentative")

    def test_motif_required_for_correction(self):
        with self.assertRaises(ValidationError):
            services.record_dues_status(actor=self.president, record=self.record, status="PAID", amount=30, paid_on=None, motif="")

    def test_negative_amount_rejected(self):
        with self.assertRaises(ValidationError):
            services.record_dues_status(actor=self.president, record=self.record, status="PAID", amount=-5, paid_on=None, motif="essai")

    def test_correction_is_audited(self):
        services.record_dues_status(actor=self.president, record=self.record, status="PAID", amount=30, paid_on=timezone.localdate(), motif="Réglé en espèces")
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, "PAID")
        change = self.record.changes.get()
        self.assertEqual(change.motif, "Réglé en espèces")
        self.assertEqual(change.old_status, "TO_REGULARIZE")

    def test_no_default_amount_invented(self):
        self.assertIsNone(self.record.amount)

    def test_own_view_does_not_leak_other_member(self):
        other_record = services.ensure_record(actor=self.president, profile=self.other.member_profile, lions_year=self.year)
        self.client.force_login(self.member)
        response = self.client.get(reverse("dues:own"))
        record_ids = {record.pk for record in response.context["records"]}
        self.assertIn(self.record.pk, record_ids)
        self.assertNotIn(other_record.pk, record_ids)

    def test_member_cannot_reach_management_detail(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse("dues:manage_detail", args=[self.record.pk])).status_code, 403)
