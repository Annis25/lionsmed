from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from apps.core.tests.test_foundations import account
from apps.governance.models import Role, LionsYear, ClubState
from apps.governance import services as governance_services
from .. import services
from ..models import DuesRecord, DuesSchedule


def lions_year():
    today = timezone.localdate()
    return LionsYear.objects.create(starts_on=today.replace(month=7, day=1), ends_on=today.replace(year=today.year+1, month=7, day=1))


class DuesTranchesTests(TestCase):
    def setUp(self):
        self.tresorier = account("tresorier@example.invalid", role=Role.TRESORIER)
        self.super_admin = account("super@example.invalid", role=Role.SUPER_ADMIN)
        self.president = account("president@example.invalid", role=Role.PRESIDENT)
        self.bureau = account("bureau@example.invalid", role=Role.BUREAU)
        self.member = account("member@example.invalid", role=Role.MEMBRE)
        self.other = account("other@example.invalid", role=Role.MEMBRE)
        self.year = lions_year()
        self.record = services.ensure_record(actor=self.tresorier, profile=self.member.member_profile, lions_year=self.year)

    def test_no_default_amount_invented(self):
        self.assertIsNone(DuesSchedule.objects.filter(lions_year=self.year).first())

    def test_status_starts_to_regularize(self):
        self.assertEqual(self.record.status, "TO_REGULARIZE")
        self.assertEqual(self.record.status_label, "Non payé")

    def test_partial_when_only_one_tranche_paid(self):
        services.set_tranche_paid(actor=self.tresorier, record=self.record, tranche=1, paid=True)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, "PARTIAL")
        self.assertEqual(self.record.status_label, "Partiellement payé")

    def test_paid_when_both_tranches_paid(self):
        services.set_tranche_paid(actor=self.tresorier, record=self.record, tranche=1, paid=True)
        services.set_tranche_paid(actor=self.tresorier, record=self.record, tranche=2, paid=True)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, "PAID")

    def test_president_can_no_longer_edit_dues(self):
        with self.assertRaises(PermissionDenied):
            services.set_tranche_paid(actor=self.president, record=self.record, tranche=1, paid=True)
        with self.assertRaises(PermissionDenied):
            services.set_dues_schedule(actor=self.president, lions_year=self.year, tranche1_amount=30, tranche2_amount=30)

    def test_member_cannot_edit_dues(self):
        with self.assertRaises(PermissionDenied):
            services.set_tranche_paid(actor=self.member, record=self.record, tranche=1, paid=True)

    def test_super_admin_can_edit(self):
        services.set_tranche_paid(actor=self.super_admin, record=self.record, tranche=2, paid=True)
        self.record.refresh_from_db()
        self.assertTrue(self.record.tranche2_paid)

    def test_negative_schedule_amount_rejected(self):
        with self.assertRaises(ValidationError):
            services.set_dues_schedule(actor=self.tresorier, lions_year=self.year, tranche1_amount=-5, tranche2_amount=30)

    def test_schedule_is_club_wide_not_per_member(self):
        services.set_dues_schedule(actor=self.tresorier, lions_year=self.year, tranche1_amount=30, tranche2_amount=40)
        self.assertEqual(DuesSchedule.objects.filter(lions_year=self.year).count(), 1)

    def test_change_is_audited_with_tranche_and_motif(self):
        services.set_tranche_paid(actor=self.tresorier, record=self.record, tranche=1, paid=True, motif="Réglé en espèces")
        change = self.record.changes.get()
        self.assertEqual(change.tranche, 1)
        self.assertTrue(change.new_paid)
        self.assertEqual(change.motif, "Réglé en espèces")

    def test_no_change_logged_when_value_unchanged(self):
        services.set_tranche_paid(actor=self.tresorier, record=self.record, tranche=1, paid=False)
        self.assertEqual(self.record.changes.count(), 0)

    def test_own_view_does_not_leak_other_member(self):
        other_record = services.ensure_record(actor=self.tresorier, profile=self.other.member_profile, lions_year=self.year)
        self.client.force_login(self.member)
        response = self.client.get(reverse("dues:own"))
        record_ids = {record.pk for record in response.context["records"]}
        self.assertIn(self.record.pk, record_ids)
        self.assertNotIn(other_record.pk, record_ids)

    def test_bureau_and_president_can_view_but_not_edit(self):
        for actor in [self.bureau, self.president]:
            with self.subTest(actor=actor.email):
                self.client.force_login(actor)
                self.assertEqual(self.client.get(reverse("dues:manage_list")).status_code, 200)
                self.assertEqual(self.client.get(reverse("dues:manage_detail", args=[self.record.pk])).status_code, 200)
                response = self.client.post(reverse("dues:manage_toggle_tranche", args=[self.record.pk, 1]))
                self.assertEqual(response.status_code, 403)

    def test_member_cannot_reach_management_pages(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse("dues:manage_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("dues:manage_detail", args=[self.record.pk])).status_code, 403)

    def test_treasurer_toggle_via_view(self):
        self.client.force_login(self.tresorier)
        response = self.client.post(reverse("dues:manage_toggle_tranche", args=[self.record.pk, 1]))
        self.assertEqual(response.status_code, 302)
        self.record.refresh_from_db()
        self.assertTrue(self.record.tranche1_paid)

    def test_toggle_rejects_external_referer(self):
        self.client.force_login(self.tresorier)
        response = self.client.post(
            reverse("dues:manage_toggle_tranche", args=[self.record.pk, 1]),
            HTTP_REFERER="https://example.invalid/phishing",
        )
        self.assertRedirects(response, reverse("dues:manage_list"))

    def test_schedule_view_requires_edit_capability(self):
        ClubState.objects.update_or_create(pk=1, defaults={"active_year": self.year})
        self.client.force_login(self.bureau)
        self.assertEqual(self.client.get(reverse("dues:manage_schedule")).status_code, 403)
        self.client.force_login(self.tresorier)
        response = self.client.post(reverse("dues:manage_schedule"), {"tranche1_amount": "30", "tranche2_amount": "40"})
        self.assertRedirects(response, reverse("dues:manage_list"))
        schedule = DuesSchedule.objects.get(lions_year=self.year)
        self.assertEqual(schedule.tranche1_amount, 30)
        self.assertEqual(schedule.tranche2_amount, 40)

    def test_directory_and_management_list_show_dues_badge(self):
        services.set_tranche_paid(actor=self.tresorier, record=self.record, tranche=1, paid=True)
        self.member.member_profile.directory_visible = True
        self.member.member_profile.save(update_fields=["directory_visible"])
        ClubState.objects.update_or_create(pk=1, defaults={"active_year": self.year})
        self.client.force_login(self.member)
        response = self.client.get(reverse("members:directory"))
        self.assertContains(response, "Partiellement payé")
        self.client.force_login(self.president)
        response = self.client.get(reverse("governance:members"))
        self.assertContains(response, "Partiellement payé")
