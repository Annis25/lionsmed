from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp.oath import TOTP
from apps.core.tests.test_foundations import account, PASSWORD
from apps.core.models import AuditEvent
from apps.governance.models import Role
from .. import mfa


def current_code(device, step_offset=0):
    import time
    totp = TOTP(device.bin_key)
    totp.time = time.time() + step_offset * 30
    return str(totp.token()).zfill(6)


class MfaCapabilityTests(TestCase):
    def test_member_cannot_manage_mfa(self):
        member = account("member@example.invalid", role=Role.MEMBRE)
        self.client.force_login(member)
        self.assertEqual(self.client.get(reverse("accounts:mfa_setup")).status_code, 403)

    def test_president_can_reach_setup(self):
        president = account("president@example.invalid", role=Role.PRESIDENT)
        self.client.force_login(president)
        self.assertEqual(self.client.get(reverse("accounts:mfa_setup")).status_code, 200)


class MfaEnrollmentTests(TestCase):
    def setUp(self):
        self.president = account("president@example.invalid", role=Role.PRESIDENT)
        self.client.force_login(self.president)

    def test_wrong_code_does_not_confirm_device(self):
        self.client.get(reverse("accounts:mfa_setup"))  # crée le device en attente
        response = self.client.post(reverse("accounts:mfa_setup"), {"token": "000000"})
        self.assertContains(response, "Code invalide")
        self.assertFalse(mfa.has_confirmed_device(self.president))

    def test_correct_code_confirms_and_issues_recovery_codes(self):
        self.client.get(reverse("accounts:mfa_setup"))
        device = TOTPDevice.objects.get(user=self.president, confirmed=False)
        response = self.client.post(reverse("accounts:mfa_setup"), {"token": current_code(device)})
        self.assertTrue(mfa.has_confirmed_device(self.president))
        self.assertContains(response, "Codes de récupération")
        self.assertTrue(AuditEvent.objects.filter(action="mfa.enabled").exists())

    def test_disable_requires_current_password(self):
        self.client.get(reverse("accounts:mfa_setup"))
        device = TOTPDevice.objects.get(user=self.president, confirmed=False)
        mfa.confirm_device(user=self.president, device=device, token=current_code(device))
        response = self.client.post(reverse("accounts:mfa_setup"), {"password": "wrong-password"})
        self.assertContains(response, "Mot de passe incorrect")
        self.assertTrue(mfa.has_confirmed_device(self.president))
        response = self.client.post(reverse("accounts:mfa_setup"), {"password": PASSWORD})
        self.assertFalse(mfa.has_confirmed_device(self.president))
        self.assertTrue(AuditEvent.objects.filter(action="mfa.disabled").exists())


class MfaLoginFlowTests(TestCase):
    def setUp(self):
        self.president = account("president@example.invalid", role=Role.PRESIDENT)
        self.member = account("member@example.invalid", role=Role.MEMBRE)
        device = TOTPDevice.objects.create(user=self.president, name="default", confirmed=False)
        self.codes = mfa.confirm_device(user=self.president, device=device, token=current_code(device))
        self.device = TOTPDevice.objects.get(pk=device.pk)

    def test_non_privileged_login_skips_mfa(self):
        response = self.client.post(reverse("accounts:login"), {"username": "member@example.invalid", "password": PASSWORD})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/espace/")

    def test_privileged_login_requires_second_factor(self):
        response = self.client.post(reverse("accounts:login"), {"username": "president@example.invalid", "password": PASSWORD})
        self.assertRedirects(response, reverse("accounts:mfa_verify"))
        # Session non authentifiée tant que le second facteur n'est pas validé.
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 302)

    def test_second_factor_wrong_code_rejected(self):
        self.client.post(reverse("accounts:login"), {"username": "president@example.invalid", "password": PASSWORD})
        response = self.client.post(reverse("accounts:mfa_verify"), {"token": "000000"})
        self.assertContains(response, "Code invalide")
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 302)

    def test_second_factor_correct_code_completes_login(self):
        # setUp a déjà consommé le pas TOTP courant lors de la confirmation : un nouveau pas est nécessaire.
        self.client.post(reverse("accounts:login"), {"username": "president@example.invalid", "password": PASSWORD})
        self.client.post(reverse("accounts:mfa_verify"), {"token": current_code(self.device, step_offset=1)})
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 200)

    def test_recovery_code_works_once_only(self):
        code = self.codes[0]
        self.client.post(reverse("accounts:login"), {"username": "president@example.invalid", "password": PASSWORD})
        self.client.post(reverse("accounts:mfa_verify"), {"token": code})
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 200)
        self.client.post(reverse("accounts:logout"))
        self.client.post(reverse("accounts:login"), {"username": "president@example.invalid", "password": PASSWORD})
        response = self.client.post(reverse("accounts:mfa_verify"), {"token": code})
        self.assertContains(response, "Code invalide")  # code déjà consommé

    def test_mfa_verify_throttled(self):
        self.client.post(reverse("accounts:login"), {"username": "president@example.invalid", "password": PASSWORD})
        for _ in range(10):
            self.client.post(reverse("accounts:mfa_verify"), {"token": "000000"})
        response = self.client.post(reverse("accounts:mfa_verify"), {"token": "000000"})
        self.assertEqual(response.status_code, 429)
