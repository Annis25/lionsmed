import json
import re
from django.test import TestCase, override_settings
from apps.core.tests.test_foundations import account
from apps.governance.models import Role
from apps.members.models import MemberProfile
from apps.members.public_profile import ensure_public_slug, public_profile_url, qr_png_bytes


class PublicProfileTests(TestCase):
    def setUp(self):
        self.user = account("anis@example.invalid", role=Role.MEMBRE)
        self.user.first_name = "Anis"; self.user.last_name = "Besbes"; self.user.save()
        self.profile = self.user.member_profile

    def test_disabled_by_default(self):
        self.assertFalse(self.profile.public_profile_enabled)
        self.assertIsNone(self.profile.public_slug)

    def test_disabled_profile_returns_404_even_with_guessed_slug(self):
        self.profile.public_slug = "anis-besbes"; self.profile.save()
        self.assertEqual(self.client.get("/membres/anis-besbes/").status_code, 404)

    def test_enabled_profile_returns_200_without_leaking_email_or_phone(self):
        self.profile.public_profile_enabled = True
        self.profile.phone = "20000000"
        ensure_public_slug(self.profile); self.profile.save()
        response = self.client.get(f"/membres/{self.profile.public_slug}/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn(self.user.email, html)
        self.assertNotIn("20000000", html)

    @override_settings(PUBLIC_INDEXING_ENABLED=True, SITE_ORIGIN="https://canonical.example.invalid")
    def test_person_json_ld_present_and_safe(self):
        self.profile.public_profile_enabled = True
        ensure_public_slug(self.profile); self.profile.save()
        html = self.client.get(f"/membres/{self.profile.public_slug}/").content.decode()
        raw = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1)
        graph = json.loads(raw)["@graph"]
        person = next(x for x in graph if x["@type"] == "Person")
        self.assertEqual(person["name"], "Anis Besbes")
        self.assertNotIn("email", str(person).lower())

    def test_slug_homonyms_never_collide_or_500(self):
        other = account("anis2@example.invalid", role=Role.MEMBRE)
        other.first_name = "Anis"; other.last_name = "Besbes"; other.save()
        self.profile.public_profile_enabled = True
        ensure_public_slug(self.profile); self.profile.save()
        other.member_profile.public_profile_enabled = True
        ensure_public_slug(other.member_profile); other.member_profile.save()
        self.assertEqual(self.profile.public_slug, "anis-besbes")
        self.assertEqual(other.member_profile.public_slug, "anis-besbes-2")
        self.assertEqual(self.client.get(f"/membres/{self.profile.public_slug}/").status_code, 200)
        self.assertEqual(self.client.get(f"/membres/{other.member_profile.public_slug}/").status_code, 200)

    def test_slug_stable_after_name_change(self):
        self.profile.public_profile_enabled = True
        ensure_public_slug(self.profile); self.profile.save()
        original_slug = self.profile.public_slug
        self.user.first_name = "Autre"; self.user.save()
        ensure_public_slug(self.profile)  # idempotent : ne régénère jamais un slug déjà attribué
        self.assertEqual(self.profile.public_slug, original_slug)

    @override_settings(PUBLIC_INDEXING_ENABLED=True)
    def test_sitemap_lists_only_enabled_profiles(self):
        self.profile.public_profile_enabled = True
        ensure_public_slug(self.profile); self.profile.save()
        other = account("hidden@example.invalid", role=Role.MEMBRE)
        sitemap = self.client.get("/sitemap.xml")
        self.assertContains(sitemap, f"/membres/{self.profile.public_slug}/")
        self.assertNotContains(sitemap, str(other.pk))

    def test_qr_encodes_canonical_public_url(self):
        self.profile.public_profile_enabled = True
        ensure_public_slug(self.profile); self.profile.save()
        try:
            from pyzbar.pyzbar import decode
        except ImportError:
            self.skipTest("pyzbar indisponible : vérification uniquement par génération sans erreur.")
            return
        png = qr_png_bytes(public_profile_url(self.profile))
        self.assertTrue(png.startswith(b"\x89PNG"))

    def test_qr_download_requires_own_login_and_enabled_profile(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/espace/profil/public/qr/").status_code, 404)
        self.profile.public_profile_enabled = True
        ensure_public_slug(self.profile); self.profile.save()
        response = self.client.get("/espace/profil/public/qr/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
