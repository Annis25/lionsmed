from uuid import uuid4

from django.test import TestCase
from django.urls import reverse

from apps.core.models import AuditEvent
from apps.core.permissions import CAPABILITIES, can, effective_role
from apps.core.tests.test_foundations import account
from apps.governance.forms import ASSIGNABLE_ROLES
from apps.governance.models import Role
from apps.communications.models import MemberEmailCampaign


class MarketingRoleTests(TestCase):
    def setUp(self):
        self.user = account("marketing@example.invalid", role=Role.MARKETING_COMMUNICATION)
        self.client.force_login(self.user)

    def test_exact_capabilities_and_assignable_role(self):
        self.assertEqual(effective_role(self.user), Role.MARKETING_COMMUNICATION)
        self.assertIn((Role.MARKETING_COMMUNICATION, "Marketing & Communication"), ASSIGNABLE_ROLES)
        expected = {
            "account.access_private_area", "account.change_own_password",
            "profile.view_own", "profile.edit_own", "experience.manage_own",
            "directory.view", "member.view", "event.register", "document.view",
            "notification.view_own", "dues.view_own", "vote.cast", "vote.view_results",
            "satisfaction.respond", "public_content.access_management", "action.create",
            "action.edit", "action.publish", "editorial.manage", "image.manage",
            "communication.send_member_broadcast", "communication.view_member_broadcast",
        }
        self.assertEqual({key for key in CAPABILITIES if can(self.user, key)}, expected)

    def test_allowed_get_and_post_routes(self):
        for route, args in [
            ("editorial_management:dashboard", []),
            ("editorial_management:list", ["action"]),
            ("editorial_management:add", ["action"]),
            ("editorial_management:image_upload", []),
            ("editorial_management:identity", []),
            ("communications:broadcast", []),
        ]:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(reverse(route, args=args)).status_code, 200)
        # Invalid forms are rendered, not rejected by permission checks.
        for route, args in [("editorial_management:add", ["action"]),
                            ("editorial_management:image_upload", [])]:
            self.assertEqual(self.client.post(reverse(route, args=args), {}).status_code, 200)

    def test_forbidden_direct_get_and_post_have_no_success_audit(self):
        before = AuditEvent.objects.count()
        for url in ["/espace/demandes/application/", "/espace/demandes/contact/",
                    "/espace/contenu/event/ajouter/", reverse("voting:manage_create"),
                    "/espace/satisfaction/gestion/", "/espace/cotisations/gestion/",
                    reverse("governance:members"), reverse("governance:years"),
                    reverse("documents:upload")]:
            for method in [self.client.get, self.client.post]:
                with self.subTest(url=url, method=method.__name__):
                    self.assertEqual(method(url).status_code, 403)
        self.assertEqual(AuditEvent.objects.count(), before)

    def test_broadcast_double_submission_creates_one_campaign(self):
        payload = {"subject": "Vie du club", "body": "Information aux membres.",
                   "campaign_key": str(uuid4()), "action": "send", "confirmed": "yes"}
        url = reverse("communications:broadcast")
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        self.assertEqual(MemberEmailCampaign.objects.count(), 1)
