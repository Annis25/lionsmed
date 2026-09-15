from decimal import Decimal
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from apps.core.tests.test_foundations import account
from apps.governance.models import Role, ClubState
from apps.members.models import MemberProfile
from apps.dues.models import DuesRecord, DuesSchedule
from apps.dues.selectors import collection_summary
from apps.dues.tests.test_dues import lions_year


class CollectionSummaryTests(TestCase):
    def setUp(self):
        self.treasurer = account("collection-treasurer@example.invalid", role=Role.TRESORIER)
        self.member = account("collection-member@example.invalid")
        self.unpaid = account("collection-unpaid@example.invalid")
        self.year = lions_year()
        ClubState.objects.update_or_create(pk=1, defaults={"active_year": self.year})

    def test_unequal_tranches_and_missing_record(self):
        DuesSchedule.objects.create(lions_year=self.year, tranche1_amount=Decimal("100.25"), tranche2_amount=Decimal("200.50"))
        DuesRecord.objects.create(profile=self.member.member_profile, lions_year=self.year, tranche1_paid=True)
        DuesRecord.objects.create(profile=self.treasurer.member_profile, lions_year=self.year, tranche2_paid=True)
        for role in (Role.SUPER_ADMIN, Role.INVITE):
            excluded = account(f"collection-{role}@example.invalid", role=role)
            DuesRecord.objects.create(profile=excluded.member_profile, lions_year=self.year, tranche1_paid=True, tranche2_paid=True)
        inactive = account("collection-inactive@example.invalid", is_active=False)
        suspended = account("collection-suspended@example.invalid")
        MemberProfile.objects.filter(user=suspended).update(status="SUSPENDED")
        for user in (inactive, suspended):
            DuesRecord.objects.create(profile=user.member_profile, lions_year=self.year, tranche1_paid=True, tranche2_paid=True)
        summary = collection_summary(self.treasurer, self.year)
        self.assertEqual(summary["member_count"], 3)
        self.assertEqual(summary["collected"], Decimal("300.75"))
        self.assertEqual(summary["remaining"], Decimal("601.50"))
        self.assertEqual(summary["expected"], Decimal("902.25"))
        self.client.force_login(self.treasurer)
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, "Cotisations encaissées")
        self.assertContains(response, "Reste à encaisser")
        self.assertContains(response, 'value="33.3"')

    def test_unconfigured_zero_and_no_year(self):
        self.assertFalse(collection_summary(self.treasurer, None)["configured"])
        self.assertIsNone(collection_summary(self.treasurer, self.year)["collected"])
        schedule = DuesSchedule.objects.create(lions_year=self.year, tranche1_amount=0)
        self.assertFalse(collection_summary(self.treasurer, self.year)["configured"])
        schedule.tranche2_amount = 0
        schedule.save()
        summary = collection_summary(self.treasurer, self.year)
        self.assertTrue(summary["configured"])
        self.assertEqual(summary["remaining"], 0)
        self.assertEqual(summary["rate"], 0)

    def test_permission_and_dashboard_visibility(self):
        for role in (Role.MEMBRE, Role.PRESIDENT, Role.SECRETAIRE, Role.MARKETING_COMMUNICATION):
            user = account(f"collection-forbidden-{role}@example.invalid", role=role)
            with self.assertRaises(PermissionDenied):
                collection_summary(user, self.year)
            self.client.force_login(user)
            self.assertNotContains(self.client.get(reverse("core:dashboard")), "titre-encaissement")
        admin = account("collection-admin@example.invalid", role=Role.SUPER_ADMIN)
        self.assertFalse(collection_summary(admin, self.year)["configured"])
