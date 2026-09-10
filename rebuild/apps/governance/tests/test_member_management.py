from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from apps.core.tests.test_foundations import account
from apps.core.permissions import effective_role
from apps.governance.models import Role, RoleGrant, LionsYear
from apps.governance import services
from apps.members.models import MemberProfile


class CreateMemberTests(TestCase):
    def setUp(self):
        self.president = account("president@example.invalid", role=Role.PRESIDENT)
        self.member = account("member@example.invalid", role=Role.MEMBRE)

    def test_member_cannot_create_accounts(self):
        with self.assertRaises(PermissionDenied):
            services.create_member(actor=self.member, first_name="A", last_name="B", email="a@example.invalid", role=Role.MEMBRE)

    def test_president_creates_account_with_unusable_password_and_role(self):
        user = services.create_member(actor=self.president, first_name="Nouvelle", last_name="Recrue",
            email="recrue@example.invalid", role=Role.BUREAU)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(effective_role(user), Role.BUREAU)
        self.assertEqual(user.member_profile.status, MemberProfile.Status.ACTIVE)

    def test_create_with_invite_role_gets_guest_status(self):
        user = services.create_member(actor=self.president, first_name="Invité", last_name="Test",
            email="invite@example.invalid", role=Role.INVITE)
        self.assertEqual(user.member_profile.status, MemberProfile.Status.GUEST)

    def test_cannot_create_super_admin_from_this_page(self):
        with self.assertRaises(ValidationError):
            services.create_member(actor=self.president, first_name="X", last_name="Y",
                email="x@example.invalid", role=Role.SUPER_ADMIN)

    def test_duplicate_email_refused(self):
        with self.assertRaises(ValidationError):
            services.create_member(actor=self.president, first_name="Dup", last_name="Licate",
                email="member@example.invalid", role=Role.MEMBRE)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_view_creates_account_and_queues_activation_link(self):
        from apps.communications.models import OutboxMessage
        from apps.communications.outbox import deliver_batch
        self.client.force_login(self.president)
        response = self.client.post(reverse("governance:member_add"), {
            "first_name": "Web", "last_name": "Recrue", "email": "web-recrue@example.invalid", "role": "MEMBRE",
        })
        user = MemberProfile.objects.get(user__email="web-recrue@example.invalid").user
        self.assertRedirects(response, reverse("governance:member", args=[user.pk]))
        # L'invitation est mise en file d'attente, pas envoyée en direct : elle ne part
        # qu'au passage du worker `deliver_outbox` (architecture outbox asynchrone).
        self.assertTrue(OutboxMessage.objects.filter(kind="ACTIVATION", recipient=user.email, state="PENDING").exists())
        self.assertEqual(len(mail.outbox), 0)
        report = deliver_batch(limit=5)
        self.assertEqual(report, {"sent": 1, "failed": 0, "disabled": False})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("web-recrue@example.invalid", mail.outbox[0].to)


class SetRoleStatusEmailTests(TestCase):
    def setUp(self):
        self.president = account("president2@example.invalid", role=Role.PRESIDENT)
        self.member = account("member2@example.invalid", role=Role.MEMBRE)
        self.super_admin = account("super2@example.invalid", role=Role.SUPER_ADMIN)

    def test_set_role_revokes_previous_grant(self):
        services.set_role(actor=self.president, target_user=self.member, role=Role.BUREAU)
        self.assertEqual(effective_role(self.member), Role.BUREAU)
        self.assertEqual(RoleGrant.objects.filter(user=self.member).count(), 2)
        self.assertEqual(RoleGrant.objects.filter(user=self.member, revoked_at__isnull=False).count(), 1)

    def test_cannot_set_role_to_super_admin(self):
        with self.assertRaises(ValidationError):
            services.set_role(actor=self.president, target_user=self.member, role=Role.SUPER_ADMIN)

    def test_cannot_change_role_of_super_admin(self):
        with self.assertRaises(PermissionDenied):
            services.set_role(actor=self.president, target_user=self.super_admin, role=Role.MEMBRE)

    def test_cannot_change_status_of_super_admin(self):
        with self.assertRaises(PermissionDenied):
            services.set_member_status(actor=self.president, profile=self.super_admin.member_profile, status=MemberProfile.Status.SUSPENDED)

    def test_cannot_change_email_of_super_admin(self):
        with self.assertRaises(PermissionDenied):
            services.set_member_email(actor=self.president, target_user=self.super_admin, email="new@example.invalid")

    def test_set_status_updates_profile(self):
        services.set_member_status(actor=self.president, profile=self.member.member_profile, status=MemberProfile.Status.SUSPENDED)
        self.member.member_profile.refresh_from_db()
        self.assertEqual(self.member.member_profile.status, MemberProfile.Status.SUSPENDED)

    def test_set_email_updates_login_identifier(self):
        services.set_member_email(actor=self.president, target_user=self.member, email="nouveau@example.invalid")
        self.member.refresh_from_db()
        self.assertEqual(self.member.email, "nouveau@example.invalid")

    def test_set_email_rejects_duplicate(self):
        with self.assertRaises(ValidationError):
            services.set_member_email(actor=self.president, target_user=self.member, email="president2@example.invalid")

    def test_member_cannot_use_management_endpoints(self):
        self.client.force_login(self.member)
        for url in [
            reverse("governance:member_set_role", args=[self.member.pk]),
            reverse("governance:member_set_status", args=[self.member.pk]),
            reverse("governance:member_set_email", args=[self.member.pk]),
        ]:
            self.assertEqual(self.client.post(url, {}).status_code, 403)

    def test_detail_page_hides_edit_forms_for_super_admin(self):
        self.client.force_login(self.president)
        response = self.client.get(reverse("governance:member", args=[self.super_admin.pk]))
        self.assertNotIn("role_form", response.context)

    def test_detail_page_offers_edit_forms_for_regular_member(self):
        self.client.force_login(self.president)
        response = self.client.get(reverse("governance:member", args=[self.member.pk]))
        self.assertIn("role_form", response.context)

    def test_role_change_via_view(self):
        self.client.force_login(self.president)
        self.client.post(reverse("governance:member_set_role", args=[self.member.pk]), {"role": "SECRETAIRE"})
        self.assertEqual(effective_role(self.member), Role.SECRETAIRE)


class LionsYearManagementTests(TestCase):
    def setUp(self):
        self.president = account("president3@example.invalid", role=Role.PRESIDENT)
        self.member = account("member3@example.invalid", role=Role.MEMBRE)

    def test_member_cannot_create_year(self):
        with self.assertRaises(PermissionDenied):
            services.create_lions_year(actor=self.member, start_year=2026)

    def test_create_year_uses_july_to_july_calendar(self):
        from datetime import date
        year = services.create_lions_year(actor=self.president, start_year=2026)
        self.assertEqual(year.starts_on, date(2026, 7, 1))
        self.assertEqual(year.ends_on, date(2027, 7, 1))
        self.assertEqual(year.label, "2026–2027")

    def test_overlapping_year_rejected(self):
        services.create_lions_year(actor=self.president, start_year=2026)
        with self.assertRaises(ValidationError):
            services.create_lions_year(actor=self.president, start_year=2026)

    def test_set_active_year(self):
        from apps.governance.models import ClubState
        year = services.create_lions_year(actor=self.president, start_year=2026)
        services.set_active_year(actor=self.president, lions_year=year)
        self.assertEqual(ClubState.objects.get(pk=1).active_year, year)

    def test_archive_toggle(self):
        year = services.create_lions_year(actor=self.president, start_year=2026)
        services.set_year_archived(actor=self.president, lions_year=year, archived=True)
        year.refresh_from_db()
        self.assertIsNotNone(year.archived_at)
        services.set_year_archived(actor=self.president, lions_year=year, archived=False)
        year.refresh_from_db()
        self.assertIsNone(year.archived_at)

    def test_view_create_and_activate(self):
        self.client.force_login(self.president)
        self.client.post(reverse("governance:years"), {"start_year": "2027"})
        year = LionsYear.objects.get(starts_on__year=2027)
        response = self.client.post(reverse("governance:year_activate", args=[year.pk]))
        self.assertRedirects(response, reverse("governance:years"))
        from apps.governance.models import ClubState
        self.assertEqual(ClubState.objects.get(pk=1).active_year_id, year.pk)

    def test_plain_member_cannot_access_manage_endpoints(self):
        year = services.create_lions_year(actor=self.president, start_year=2028)
        self.client.force_login(self.member)
        self.assertEqual(self.client.post(reverse("governance:year_activate", args=[year.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("governance:year_archive_toggle", args=[year.pk])).status_code, 403)

    def test_plain_member_has_no_view_access_at_all(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse("governance:years")).status_code, 403)

    def test_manager_sees_creation_form(self):
        self.client.force_login(self.president)
        response = self.client.get(reverse("governance:years"))
        self.assertContains(response, "Créer une Année Lions")


class NewOfficerRolesTests(TestCase):
    def setUp(self):
        self.president = account("president4@example.invalid", role=Role.PRESIDENT)

    def test_new_roles_assignable_and_not_elevated_by_default(self):
        from apps.core.permissions import can
        for role in [Role.VICE_PRESIDENT, Role.TRESORIER, Role.GST, Role.GMT, Role.GLT, Role.LCIF]:
            with self.subTest(role=role):
                user = services.create_member(actor=self.president, first_name="Officier", last_name=role,
                    email=f"{role.lower()}@example.invalid", role=role)
                self.assertEqual(effective_role(user), role)
                # Aucune capacité de gestion inventée pour ces nouveaux rôles.
                self.assertFalse(can(user, "vote.manage"))
                self.assertFalse(can(user, "document.manage"))
                self.assertFalse(can(user, "members.manage"))
                # Mais bien les capacités de base d'un membre.
                self.assertTrue(can(user, "vote.cast"))
                self.assertTrue(can(user, "directory.view"))

    def test_new_roles_appear_in_assignable_choices(self):
        from apps.governance.forms import ASSIGNABLE_ROLES
        values = {value for value, _ in ASSIGNABLE_ROLES}
        self.assertTrue({"VICE_PRESIDENT", "TRESORIER", "GST", "GMT", "GLT", "LCIF"} <= values)
        self.assertNotIn("SUPER_ADMIN", values)


class PresidentFondateurRoleTests(TestCase):
    """Rôle ajouté à la demande explicite du club, avec les mêmes capacités que
    Président (palier MANAGERS) — décision confirmée, contrairement aux autres
    nouveaux rôles officiers qui n'ont volontairement aucune capacité élevée."""

    def setUp(self):
        self.president = account("president5@example.invalid", role=Role.PRESIDENT)
        self.fondateur = services.create_member(actor=self.president, first_name="Fondateur", last_name="Historique",
            email="fondateur@example.invalid", role=Role.PRESIDENT_FONDATEUR)

    def test_assignable_and_appears_in_choices(self):
        from apps.governance.forms import ASSIGNABLE_ROLES
        self.assertEqual(effective_role(self.fondateur), Role.PRESIDENT_FONDATEUR)
        values = {value for value, _ in ASSIGNABLE_ROLES}
        self.assertIn("PRESIDENT_FONDATEUR", values)

    def test_has_same_manager_level_capabilities_as_president(self):
        from apps.core.permissions import can
        manager_capabilities = ["event.create", "action.create", "editorial.manage", "members.manage",
            "members.view_management", "management.access", "year.manage", "document.manage",
            "notification.send", "vote.manage", "satisfaction.manage", "statistics.view",
            "attendance.record", "mfa.manage_own"]
        for capability in manager_capabilities:
            with self.subTest(capability=capability):
                self.assertEqual(can(self.fondateur, capability), can(self.president, capability))
                self.assertTrue(can(self.fondateur, capability))

    def test_narrower_president_specific_inboxes_not_included(self):
        """Périmètre volontairement plus étroit que Président sur ces trois points
        précis (boîtes de contact/candidature, diffusion Bureau) : à élargir seulement
        sur nouvelle confirmation explicite du club."""
        from apps.core.permissions import can
        self.assertFalse(can(self.fondateur, "contact.manage"))
        self.assertFalse(can(self.fondateur, "application.manage"))
        self.assertFalse(can(self.fondateur, "communication.send_member_broadcast"))
