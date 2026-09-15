from uuid import uuid4
from django.test import TestCase, Client
from django.urls import reverse
from apps.core.tests.test_foundations import account
from apps.governance.models import Role, ClubState
from apps.dues.tests.test_dues import lions_year
from apps.dues.models import DuesRecord


class WorkspaceTests(TestCase):
    def setUp(self):
        self.treasurer = account("workspace-treasurer@example.invalid", role=Role.TRESORIER)
        self.member = account("workspace-member@example.invalid")
        self.member.first_name = "Membre"
        self.member.save(update_fields=["first_name"])
        self.year = lions_year()
        ClubState.objects.update_or_create(pk=1, defaults={"active_year": self.year})
        self.url = reverse("dues:manage_set", args=[self.year.pk, self.member.member_profile.pk, 1])

    def test_all_members_and_idempotent_payment(self):
        self.client.force_login(self.treasurer)
        self.assertContains(self.client.get(reverse("dues:manage_list")), "Membre Synthétique")
        data = {"paid": "1", "paid_on": "2026-09-15", "motif": "Test"}
        for _ in range(2):
            self.assertEqual(self.client.post(self.url, data).status_code, 302)
        record = DuesRecord.objects.get(profile=self.member.member_profile, lions_year=self.year)
        self.assertTrue(record.tranche1_paid)
        self.assertEqual(record.changes.count(), 1)
        result = self.client.get(reverse("dues:manage_list"), {"status": "PARTIAL", "q": "Synthétique"})
        self.assertEqual(result.context["page_obj"].paginator.count, 1)
        self.assertEqual(result.context["counts"]["partial"], 1)

    def test_permissions_missing_objects_and_csrf(self):
        for role in (Role.MEMBRE, Role.PRESIDENT, Role.SECRETAIRE):
            actor = account(f"workspace-{role}@example.invalid", role=role)
            self.client.force_login(actor)
            self.assertEqual(self.client.post(self.url, {"paid": "1"}).status_code, 403)
        self.client.force_login(self.treasurer)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertEqual(self.client.post(reverse("dues:manage_set", args=[999999, self.member.member_profile.pk, 1]), {"paid": "1"}).status_code, 404)
        self.assertEqual(self.client.post(reverse("dues:manage_set", args=[self.year.pk, 999999, 1]), {"paid": "1"}).status_code, 404)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.treasurer)
        self.assertEqual(client.post(self.url, {"paid": "1"}).status_code, 403)
        super_admin = account("workspace-super@example.invalid", role=Role.SUPER_ADMIN)
        self.client.force_login(super_admin)
        self.assertEqual(self.client.post(self.url, {"paid": "1"}).status_code, 302)

    def test_suggestions_cover_club_not_only_filtered_page(self):
        from apps.members.models import MemberProfile
        from apps.dues.selectors import workspace_members
        from django.core.exceptions import PermissionDenied
        for index in range(22):
            user = account(f"suggest-{index}@example.invalid")
            user.first_name = f"Suggestion{index}"
            user.save(update_fields=["first_name"])
        for role in (Role.INVITE, Role.SUPER_ADMIN):
            account(f"excluded-{role}@example.invalid", role=role)
        inactive = account("suggest-inactive@example.invalid", is_active=False)
        suspended = account("suggest-suspended@example.invalid")
        MemberProfile.objects.filter(user=suspended).update(status="SUSPENDED")
        self.client.force_login(self.treasurer)
        response = self.client.get(reverse("dues:manage_list"), {"q": "Membre", "status": "PARTIAL", "page": "2"})
        self.assertEqual(response.context["page_obj"].paginator.count, 0)
        names = response.context["member_suggestions"]
        self.assertIn("Suggestion21 Synthétique", names)
        self.assertIn("Membre Synthétique", names)
        ids = {profile.user_id for profile in workspace_members(self.treasurer)}
        self.assertNotIn(inactive.pk, ids)
        self.assertNotIn(suspended.pk, ids)
        self.assertContains(response, 'list="dues-member-names"')
        with self.assertRaises(PermissionDenied):
            workspace_members(self.member)
