"""Parcours « créer une action puis la publier » dans l'espace de gestion : ce que voit et
comprend la personne qui saisit, quand tout va bien et quand quelque chose est refusé."""
import tempfile
from datetime import timedelta
from io import BytesIO
from PIL import Image
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from apps.core.image_processing import MAX_BYTES
from apps.core.tests.test_foundations import account
from apps.editorial.publication import publish_content
from apps.governance.models import Role
from apps.service_actions.models import Action, ActionPhoto
from .test_public import content


def photo(name="photo.jpg", size=(1200, 800), color="blue"):
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, "JPEG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


def fields(**changes):
    data = {"title": "Dépistage au marché", "axis": "DIABETE", "summary": "Résumé", "body": "Récit",
            "performed_on": str(timezone.localdate()), "location": "Marché central", "intent": "draft"}
    data.update(changes)
    return data


class ActionManagementTests(TestCase):
    def setUp(self):
        self.actor = account("contenu@example.invalid", role=Role.MARKETING_COMMUNICATION)
        self.client.force_login(self.actor)
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        images = override_settings(PUBLIC_IMAGE_ROOT=root.name)
        images.enable()
        self.addCleanup(images.disable)
        self.add_url = reverse("editorial_management:add", kwargs={"kind": "action"})

    def edit_url(self, obj):
        return reverse("editorial_management:edit", kwargs={"kind": "action", "object_id": obj.pk})

    def said(self, response):
        return [str(message) for message in get_messages(response.wsgi_request)]

    def test_draft_images_are_shown_in_management_and_stay_out_of_the_public_site(self):
        self.client.post(self.add_url, fields(main_image_upload=photo(), gallery_uploads=[photo("autre.jpg")]))
        obj = Action.objects.get()
        self.assertEqual(obj.status, "DRAFT")
        gallery_image = obj.photos.get().image
        for image in (obj.cover, gallery_image):
            preview = reverse("editorial_management:image_preview", args=[image.pk, 480])
            self.assertContains(self.client.get(self.edit_url(obj)), preview)
            response = self.client.get(preview)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "image/webp")
            b"".join(response.streaming_content)
            # La route publique reste fermée tant que l'action n'est pas publiée.
            self.assertEqual(self.client.get(image.get_absolute_url()).status_code, 404)
        cover_preview = reverse("editorial_management:image_preview", args=[obj.cover.pk, 480])
        self.assertContains(self.client.get(reverse("editorial_management:list", kwargs={"kind": "action"})), cover_preview)
        self.assertEqual(self.client.get(reverse("editorial_management:image_preview", args=[obj.cover.pk, 999])).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(cover_preview).status_code, 302)
        self.client.force_login(account("membre@example.invalid", role=Role.MEMBRE))
        self.assertEqual(self.client.get(cover_preview).status_code, 403)

    def test_refused_publication_at_creation_keeps_one_draft_and_explains(self):
        future = str(timezone.localdate() + timedelta(days=20))
        response = self.client.post(self.add_url, fields(intent="publish", performed_on=future, location=""))
        obj = Action.objects.get()
        self.assertRedirects(response, self.edit_url(obj), fetch_redirect_response=False)
        self.assertEqual(obj.status, "DRAFT")
        said = " ".join(self.said(response))
        self.assertIn("enregistrée en brouillon, mais elle n’est pas encore publiée", said)
        self.assertIn("date de réalisation", said)
        # Seconde tentative, corrigée, sur la page de l'action : publiée, sans doublon ni message technique.
        response = self.client.post(self.edit_url(obj), fields(intent="publish"))
        self.assertRedirects(response, self.edit_url(obj), fetch_redirect_response=False)
        self.assertEqual(Action.objects.get().status, "PUBLISHED")
        self.assertIn("Action publiée", " ".join(self.said(response)))

    def test_same_title_twice_is_explained_without_technical_word(self):
        self.client.post(self.add_url, fields())
        response = self.client.post(self.add_url, fields())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Une autre action porte déjà ce titre")
        self.assertNotContains(response, "slug")
        self.assertEqual(Action.objects.count(), 1)

    def test_refused_image_is_reported_on_the_saved_action(self):
        too_large = photo("geante.jpg", size=(4100, 4100))  # plus de 16 millions de pixels
        response = self.client.post(self.add_url, fields(intent="publish", main_image_upload=photo(), gallery_uploads=[too_large]))
        obj = Action.objects.get()
        self.assertRedirects(response, self.edit_url(obj), fetch_redirect_response=False)
        self.assertEqual(obj.status, "DRAFT")
        self.assertIsNotNone(obj.cover)
        self.assertEqual(obj.photos.count(), 0)
        said = " ".join(self.said(response))
        self.assertIn("Image non ajoutée — « geante.jpg »", said)
        self.assertIn("n’est pas encore publiée. Une image a été refusée.", said)

    def test_update_of_a_published_action_keeps_it_published(self):
        obj = publish_content(actor=self.actor, obj=content(self.actor), kind="action")
        response = self.client.post(self.edit_url(obj), fields(title=obj.title, intent="update", gallery_uploads=[photo()]))
        obj.refresh_from_db()
        self.assertEqual(obj.status, "PUBLISHED")
        self.assertEqual(obj.photos.count(), 1)
        self.assertIn("L’action reste publiée. 1 image ajoutée.", " ".join(self.said(response)))

    def test_removing_a_gallery_image_keeps_the_action_published_and_says_so(self):
        obj = content(self.actor)
        self.client.post(self.edit_url(obj), fields(title=obj.title, intent="publish", gallery_uploads=[photo(), photo("b.jpg")]))
        obj.refresh_from_db()
        self.assertEqual(obj.status, "PUBLISHED")
        first = obj.photos.first()
        response = self.client.post(reverse("editorial_management:gallery", kwargs={"object_id": obj.pk}), {"remove": first.pk})
        obj.refresh_from_db()
        self.assertEqual(obj.status, "PUBLISHED")
        self.assertFalse(ActionPhoto.objects.filter(pk=first.pk).exists())
        self.assertEqual(self.said(response)[-1], "Image retirée. L’action reste publiée.")
        self.client.logout()
        self.assertEqual(self.client.get(obj.get_absolute_url()).status_code, 200)

    def test_back_to_draft_withdraws_the_public_page_and_says_so(self):
        obj = publish_content(actor=self.actor, obj=content(self.actor), kind="action")
        response = self.client.post(reverse("editorial_management:draft", kwargs={"object_id": obj.pk}))
        self.assertRedirects(response, self.edit_url(obj), fetch_redirect_response=False)
        obj.refresh_from_db()
        self.assertEqual(obj.status, "DRAFT")
        self.assertEqual(self.said(response), ["Action remise en brouillon. Elle n’est plus visible sur le site public."])
        self.client.logout()
        self.assertEqual(self.client.get(obj.get_absolute_url()).status_code, 404)

    def test_delete_needs_an_explicit_confirmation(self):
        obj = content(self.actor)
        url = reverse("editorial_management:delete", kwargs={"object_id": obj.pk})
        response = self.client.post(url)
        self.assertRedirects(response, self.edit_url(obj), fetch_redirect_response=False)
        self.assertTrue(Action.objects.filter(pk=obj.pk).exists())
        self.assertIn("Suppression non confirmée", " ".join(self.said(response)))
        page = self.client.get(self.edit_url(obj))
        self.assertContains(page, 'name="confirmed" value="yes" required')
        response = self.client.post(url, {"confirmed": "yes"})
        self.assertRedirects(response, reverse("editorial_management:list", kwargs={"kind": "action"}), fetch_redirect_response=False)
        self.assertFalse(Action.objects.filter(pk=obj.pk).exists())

    def test_file_over_the_limit_gets_a_readable_page_and_saves_nothing(self):
        heavy = SimpleUploadedFile("lourde.jpg", b"x" * (MAX_BYTES + 1), content_type="image/jpeg")
        response = self.client.post(self.add_url, fields(main_image_upload=heavy), HTTP_REFERER="http://testserver" + self.add_url)
        self.assertEqual(response.status_code, 400)
        html = response.content.decode()
        self.assertIn("<h1>Fichier trop lourd</h1>", html)
        self.assertIn("5 Mo maximum par fichier", html)
        self.assertIn('href="http://testserver' + self.add_url + '"', html)
        self.assertNotIn("Bad Request", html)
        self.assertEqual(Action.objects.count(), 0)
        # Un lien de retour ne pointe jamais vers un autre site.
        response = self.client.post(self.add_url, fields(main_image_upload=SimpleUploadedFile("lourde.jpg", b"x" * (MAX_BYTES + 1), content_type="image/jpeg")), HTTP_REFERER="https://ailleurs.example/piege")
        self.assertNotIn("ailleurs.example", response.content.decode())

    def test_page_states_what_is_being_done_and_where_the_action_stands(self):
        listing = reverse("editorial_management:list", kwargs={"kind": "action"})
        self.assertContains(self.client.get(listing), "Créer la première action", count=1)
        self.assertNotContains(self.client.get(listing), "Créer une action")
        self.assertContains(self.client.get(self.add_url), "<h1>Nouvelle action</h1>", html=True)
        obj = content(self.actor)
        page = self.client.get(self.edit_url(obj))
        self.assertContains(page, "<h1>Modifier l’action</h1>", html=True)
        self.assertContains(page, "badge--brouillon")
        self.assertNotContains(page, "Voir la page publique")
        obj = publish_content(actor=self.actor, obj=obj, kind="action")
        page = self.client.get(self.edit_url(obj))
        self.assertContains(page, "badge--publie")
        self.assertContains(page, 'href="' + obj.get_absolute_url() + '"')
        self.assertContains(page, "Voir la page publique")
        self.assertContains(self.client.get(listing), "Créer une action", count=1)
