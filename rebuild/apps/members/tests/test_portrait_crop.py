from io import BytesIO
from tempfile import TemporaryDirectory
from PIL import Image
from django.test import TestCase, override_settings
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.core.tests.test_foundations import account
from apps.members.services import update_profile
from apps.members.uploads import photo_storage
from apps.members.tests.test_members import PROFILE


class PortraitCropTests(TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.settings_override = override_settings(PRIVATE_MEDIA_ROOT=self.folder.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.user = account("crop@example.invalid")
        self.profile = self.user.member_profile
        self.client.force_login(self.user)

    def upload(self):
        image = Image.new("RGB", (200, 400), "red")
        image.paste("blue", (0, 200, 200, 400))
        raw = BytesIO()
        image.save(raw, "PNG")
        return SimpleUploadedFile("portrait.png", raw.getvalue(), content_type="image/png")

    def save(self, **extra):
        return update_profile(actor=self.user, profile=self.profile, data={**PROFILE, **extra})

    def test_crop_and_recrop_preserve_original(self):
        self.assertIsNone(update_profile(actor=self.user, profile=self.profile,
            data={**PROFILE, "photo_zoom": "1", "photo_x": "50", "photo_y": "0"}, files={"photo": self.upload()}))
        self.profile.refresh_from_db()
        original = self.profile.photo_original_key
        with photo_storage().open(self.profile.photo_key) as handle:
            image = Image.open(handle)
            self.assertEqual(image.size, (512, 512))
            self.assertGreater(image.getpixel((256, 256))[0], 200)
        self.assertIsNone(self.save(photo_zoom="1", photo_x="50", photo_y="100"))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.photo_original_key, original)
        with photo_storage().open(self.profile.photo_key) as handle:
            self.assertGreater(Image.open(handle).getpixel((256, 256))[2], 200)
        previous = self.profile.photo_key
        self.assertIsNone(self.save())
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.photo_key, previous)

    def test_invalid_crop_refused_without_mutation(self):
        for values in [dict(photo_zoom="0"), dict(photo_zoom="5"), dict(photo_x="-1"),
                       dict(photo_y="101"), dict(photo_zoom="nan"), dict(photo_x="inf")]:
            form = self.save(**values)
            self.assertTrue(form.errors)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.photo_key, "")

    def test_original_private_endpoint_ownership_and_removal(self):
        self.assertIsNone(update_profile(actor=self.user, profile=self.profile, data=PROFILE, files={"photo": self.upload()}))
        self.profile.refresh_from_db()
        url = reverse("members:photo_original")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.client.force_login(account("crop-other@example.invalid"))
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertIsNone(self.save(remove_photo="on"))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.photo_key, "")
        self.assertEqual(self.profile.photo_original_key, "")
        self.assertEqual(self.profile.photo_crop, {})

    def test_legacy_photo_can_be_reframed(self):
        from apps.members.uploads import encode_photo
        key = photo_storage().save("portraits/legacy.jpg", encode_photo(self.upload()))
        self.profile.photo_key = key
        self.profile.save()
        self.assertIsNone(self.save(photo_zoom="2", photo_x="50", photo_y="50"))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.photo_original_key, key)
        self.assertTrue(photo_storage().exists(key))
