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

    def test_membership_line_defaults_to_membre_when_no_title_set(self):
        self.profile.public_profile_enabled = True
        ensure_public_slug(self.profile); self.profile.save()
        html = self.client.get(f"/membres/{self.profile.public_slug}/").content.decode()
        self.assertIn("Membre du Lions Club Sfax-Méditerranée", html)

    def test_membership_line_uses_custom_public_title(self):
        self.profile.public_profile_enabled = True
        self.profile.public_title = "Past President"
        ensure_public_slug(self.profile); self.profile.save()
        html = self.client.get(f"/membres/{self.profile.public_slug}/").content.decode()
        self.assertIn("Past President du Lions Club Sfax-Méditerranée", html)
        self.assertNotIn("Membre du Lions Club Sfax-Méditerranée", html)

    def test_poste_edited_in_private_profile_is_displayed_publicly(self):
        from django.urls import reverse
        from apps.members.tests.test_members import PROFILE
        self.profile.public_profile_enabled = True
        ensure_public_slug(self.profile)
        self.profile.save()
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("members:profile_edit")), "Poste au sein du club")
        response = self.client.post(reverse("members:profile_edit"), {
            **PROFILE, "public_profile_enabled": "on", "public_title": "Trésorier",
        })
        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.public_title, "Trésorier")
        response = self.client.get(f"/membres/{self.profile.public_slug}/")
        self.assertContains(response, "Trésorier du Lions Club Sfax-Méditerranée")

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

    def test_qr_generation_is_well_formed(self):
        self.profile.public_profile_enabled = True
        ensure_public_slug(self.profile); self.profile.save()
        url = public_profile_url(self.profile)
        png = qr_png_bytes(url)
        self.assertTrue(png.startswith(b"\x89PNG"))
        from io import BytesIO
        from PIL import Image
        image = Image.open(BytesIO(png))
        self.assertEqual(image.format, "PNG")
        # Carré, et assez grand pour rester net à l'impression malgré un affichage
        # écran limité à 300px (voir .qr-image) — dimension réelle non figée dans le
        # test pour ne pas coupler à la version QR choisie selon la longueur de l'URL.
        self.assertEqual(image.width, image.height)
        self.assertGreaterEqual(image.width, 400)

    def test_qr_encodes_canonical_public_url(self):
        self.profile.public_profile_enabled = True
        ensure_public_slug(self.profile); self.profile.save()
        try:
            from pyzbar.pyzbar import decode
        except ImportError:
            self.skipTest("pyzbar indisponible : lecture du QR non vérifiée dans cet environnement.")
            return
        from io import BytesIO
        from PIL import Image
        url = public_profile_url(self.profile)
        png = qr_png_bytes(url)
        decoded = decode(Image.open(BytesIO(png)))
        self.assertEqual(len(decoded), 1)
        self.assertEqual(decoded[0].data.decode(), url)

    def test_qr_download_requires_own_login_and_enabled_profile(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/espace/profil/public/qr/").status_code, 404)
        self.profile.public_profile_enabled = True
        ensure_public_slug(self.profile); self.profile.save()
        response = self.client.get("/espace/profil/public/qr/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(response["Content-Disposition"], f'attachment; filename="lionsmed-{self.profile.public_slug}-qr.png"')

    def test_qr_reveals_no_private_data(self):
        self.profile.public_profile_enabled = True
        self.profile.phone = "20000000"
        ensure_public_slug(self.profile); self.profile.save()
        url = public_profile_url(self.profile)
        self.assertNotIn("@", url)
        self.assertNotIn(self.user.email, url)
        self.assertNotIn("20000000", url)
        self.assertNotIn(str(self.user.pk), url)
        self.assertNotIn(str(self.profile.pk), url)
        self.assertNotIn("?", url)

    def test_own_profile_page_shows_qr_modal_when_public_profile_enabled(self):
        self.profile.public_profile_enabled = True
        ensure_public_slug(self.profile); self.profile.save()
        self.client.force_login(self.user)
        response = self.client.get("/espace/profil/")
        html = response.content.decode()
        self.assertContains(response, "Afficher mon QR")
        self.assertContains(response, 'id="dialog-qr"')
        self.assertContains(response, 'aria-labelledby="qr-dialog-title"')
        self.assertIn('src="data:image/png;base64,', html)
        self.assertNotIn("Activez votre profil public", html)

    def test_own_profile_page_shows_activation_message_when_public_profile_disabled(self):
        self.client.force_login(self.user)
        response = self.client.get("/espace/profil/")
        html = response.content.decode()
        self.assertContains(response, "Activez votre profil public pour générer votre QR code.")
        self.assertNotIn("Afficher mon QR", html)
        self.assertNotIn('id="dialog-qr"', html)
