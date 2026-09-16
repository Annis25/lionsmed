from io import BytesIO
from unittest.mock import patch
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from apps.core.tests.test_foundations import account
from apps.core.models import AuditEvent
from apps.governance.models import Role
from .. import services
from ..models import Document, DocumentGrant
from ..selectors import scope_documents, document_for_actor
from ..scanning import ScanResult, ScannerUnavailable


def pdf(name="doc.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4 synthetic", content_type="application/pdf")


class DocumentAclTests(TestCase):
    def setUp(self):
        self.president = account("president@example.invalid", role=Role.PRESIDENT)
        self.member = account("member@example.invalid", role=Role.MEMBRE)
        self.bureau = account("bureau@example.invalid", role=Role.BUREAU)
        self.invite = account("guest@example.invalid", role=Role.INVITE)
        self.other_member = account("other@example.invalid", role=Role.MEMBRE)
        # Le scanner antivirus réel (clamd) n'est pas disponible dans cet environnement de
        # test ; on simule un résultat "sain" pour tester l'ACL indépendamment du scanner
        # (dont le comportement fail-closed est testé séparément, voir ScanningTests).
        patcher = patch("apps.documents.services.scan_bytes", return_value=ScanResult(clean=True, detail="stream: OK"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def upload(self, visibility):
        return services.upload_document(actor=self.president, upload=pdf(), title="Titre", description="",
            category=Document.Category.GENERAL, visibility=visibility)

    def test_member_visibility_document_is_visible_to_member_not_invite(self):
        document = self.upload(Document.Visibility.MEMBERS)
        self.assertTrue(scope_documents(self.member).filter(pk=document.pk).exists())
        self.assertFalse(scope_documents(self.invite).filter(pk=document.pk).exists())

    def test_bureau_visibility_excludes_plain_member(self):
        document = self.upload(Document.Visibility.BUREAU)
        self.assertTrue(scope_documents(self.bureau).filter(pk=document.pk).exists())
        self.assertFalse(scope_documents(self.member).filter(pk=document.pk).exists())

    def test_responsables_visibility_excludes_bureau(self):
        document = self.upload(Document.Visibility.RESPONSABLES)
        self.assertTrue(scope_documents(self.president).filter(pk=document.pk).exists())
        self.assertFalse(scope_documents(self.bureau).filter(pk=document.pk).exists())

    def test_explicit_grant_authorizes_invite(self):
        document = self.upload(Document.Visibility.RESPONSABLES)
        self.assertFalse(scope_documents(self.invite).filter(pk=document.pk).exists())
        services.grant_access(actor=self.president, document=document, user=self.invite)
        self.assertTrue(scope_documents(self.invite).filter(pk=document.pk).exists())

    def test_expired_grant_does_not_authorize(self):
        document = self.upload(Document.Visibility.RESPONSABLES)
        services.grant_access(actor=self.president, document=document, user=self.invite, expires_at=timezone.now()-timedelta(days=1))
        self.assertFalse(scope_documents(self.invite).filter(pk=document.pk).exists())

    def test_list_detail_preview_and_download_share_the_same_acl(self):
        document = self.upload(Document.Visibility.RESPONSABLES)
        self.client.force_login(self.member)
        list_response = self.client.get(reverse("documents:list"))
        self.assertNotContains(list_response, document.title)
        self.assertEqual(self.client.get(reverse("documents:detail", args=[document.pk])).status_code, 404)
        self.assertEqual(self.client.head(reverse("documents:preview", args=[document.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("documents:preview", args=[document.pk])).status_code, 404)
        self.assertEqual(self.client.head(reverse("documents:download", args=[document.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("documents:download", args=[document.pk])).status_code, 404)
        self.client.force_login(self.president)
        self.assertContains(self.client.get(reverse("documents:list")), document.title)
        detail = self.client.get(reverse("documents:detail", args=[document.pk]))
        self.assertContains(detail, "Visualiser")
        preview_head = self.client.head(reverse("documents:preview", args=[document.pk]))
        self.assertEqual(preview_head.status_code, 200)
        self.assertTrue(preview_head["Content-Disposition"].startswith("inline;"))
        preview = self.client.get(reverse("documents:preview", args=[document.pk]))
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview["Cache-Control"], "private, no-store")
        self.assertEqual(preview["X-Content-Type-Options"], "nosniff")
        self.assertEqual(preview["Cross-Origin-Resource-Policy"], "same-origin")
        download_head = self.client.head(reverse("documents:download", args=[document.pk]))
        self.assertEqual(download_head.status_code, 200)
        self.assertTrue(download_head["Content-Disposition"].startswith("attachment;"))
        self.assertEqual(self.client.get(reverse("documents:download", args=[document.pk])).status_code, 200)

    def test_office_document_is_download_only_and_cannot_be_forced_inline(self):
        document = self.upload(Document.Visibility.MEMBERS)
        document.content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        document.original_filename = "document.docx"
        document.save(update_fields=["content_type", "original_filename"])
        self.client.force_login(self.member)
        detail = self.client.get(reverse("documents:detail", args=[document.pk]))
        self.assertNotContains(detail, "Visualiser")
        self.assertContains(detail, "Télécharger")
        self.assertEqual(self.client.get(reverse("documents:preview", args=[document.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("documents:download", args=[document.pk])).status_code, 200)

    def test_bureau_cannot_manage_documents(self):
        with self.assertRaises(PermissionDenied):
            services.upload_document(actor=self.bureau, upload=pdf(), title="x", description="",
                category=Document.Category.GENERAL, visibility=Document.Visibility.MEMBERS)

    def test_rejects_disguised_extension(self):
        fake = SimpleUploadedFile("doc.pdf", b"not really a pdf", content_type="application/zip")
        with self.assertRaises(ValidationError):
            services.upload_document(actor=self.president, upload=fake, title="x", description="",
                category=Document.Category.GENERAL, visibility=Document.Visibility.MEMBERS)

    def test_other_member_cannot_use_management_urls(self):
        document = self.upload(Document.Visibility.MEMBERS)
        self.client.force_login(self.other_member)
        self.assertEqual(self.client.get(reverse("documents:manage_detail", args=[document.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("documents:manage_list")).status_code, 403)

    def test_manager_can_delete_document_and_private_file_after_commit(self):
        document = self.upload(Document.Visibility.MEMBERS)
        services.grant_access(actor=self.president, document=document, user=self.invite)
        storage_key = document.storage_key
        with patch("apps.documents.services.document_storage") as storage_factory:
            with self.captureOnCommitCallbacks(execute=True):
                services.delete_document(actor=self.president, document=document)
        document.refresh_from_db()
        self.assertEqual(document.status, Document.Status.DELETED)
        self.assertFalse(DocumentGrant.objects.filter(document=document).exists())
        storage_factory.return_value.delete.assert_called_once_with(storage_key)
        self.assertFalse(scope_documents(self.member).filter(pk=document.pk).exists())
        self.assertTrue(AuditEvent.objects.filter(
            actor=self.president,
            action="document.deleted",
            object_id=str(document.pk),
        ).exists())

    def test_delete_view_is_post_only_and_removes_document_from_management(self):
        document = self.upload(Document.Visibility.MEMBERS)
        url = reverse("documents:manage_delete", args=[document.pk])
        self.client.force_login(self.president)
        self.assertEqual(self.client.get(url).status_code, 405)
        with patch("apps.documents.services.document_storage"):
            response = self.client.post(url)
        self.assertRedirects(response, reverse("documents:manage_list"))
        document.refresh_from_db()
        self.assertEqual(document.status, Document.Status.DELETED)
        self.assertEqual(self.client.get(reverse("documents:manage_detail", args=[document.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("documents:manage_list")), document.title)

    def test_member_cannot_delete_document_by_direct_post(self):
        document = self.upload(Document.Visibility.MEMBERS)
        self.client.force_login(self.member)
        response = self.client.post(reverse("documents:manage_delete", args=[document.pk]))
        self.assertEqual(response.status_code, 403)
        document.refresh_from_db()
        self.assertEqual(document.status, Document.Status.AVAILABLE)
        self.assertFalse(AuditEvent.objects.filter(action="document.deleted", object_id=str(document.pk)).exists())

    def test_management_detail_displays_confirmed_delete_action(self):
        document = self.upload(Document.Visibility.MEMBERS)
        self.client.force_login(self.president)
        response = self.client.get(reverse("documents:manage_detail", args=[document.pk]))
        self.assertContains(response, "Supprimer le document")
        self.assertContains(response, reverse("documents:manage_delete", args=[document.pk]))


class DocumentUIRedesignTests(TestCase):
    """Refonte UI/UX des 4 pages Documents — structure/contenu rendu et permissions,
    aucune règle métier changée au-delà des filtres/tri additifs déjà couverts ici."""

    def setUp(self):
        self.president = account("ui-president@example.invalid", role=Role.PRESIDENT)
        self.member = account("ui-member@example.invalid", role=Role.MEMBRE)
        self.invite = account("ui-guest@example.invalid", role=Role.INVITE)
        patcher = patch("apps.documents.services.scan_bytes", return_value=ScanResult(clean=True, detail="stream: OK"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def upload(self, **kwargs):
        data = dict(actor=self.president, upload=pdf(kwargs.pop("filename", "doc.pdf")), title="Règlement intérieur",
            description="Document synthétique", category=Document.Category.GOUVERNANCE, visibility=Document.Visibility.MEMBERS)
        data.update(kwargs)
        return services.upload_document(**data)

    def test_member_list_shows_inline_actions_and_category_badge(self):
        self.upload()
        self.client.force_login(self.member)
        response = self.client.get(reverse("documents:list"))
        self.assertContains(response, "Visualiser")
        self.assertContains(response, "Télécharger")
        self.assertContains(response, "badge--excuse")
        self.assertContains(response, "Gouvernance")

    def test_member_list_category_filter_and_sort_are_server_side(self):
        self.upload(title="A - Financier", category=Document.Category.FINANCIER)
        self.upload(title="B - District", category=Document.Category.DISTRICT)
        self.client.force_login(self.member)
        response = self.client.get(reverse("documents:list"), {"category": Document.Category.FINANCIER})
        self.assertContains(response, "A - Financier")
        self.assertNotContains(response, "B - District")
        response = self.client.get(reverse("documents:list"), {"tri": "alpha"})
        titles = [d.title for d in response.context["page_obj"]]
        self.assertEqual(titles, sorted(titles))

    def test_member_list_empty_state(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("documents:list"))
        self.assertContains(response, "Aucun document disponible")

    def test_gestion_list_shows_kpi_counts(self):
        self.upload(title="Doc 1")
        self.upload(title="Doc 2", category=Document.Category.FINANCIER)
        self.client.force_login(self.president)
        response = self.client.get(reverse("documents:manage_list"))
        self.assertEqual(response.context["counts"]["total"], 2)
        self.assertEqual(response.context["counts"]["available"], 2)
        self.assertEqual(response.context["counts"]["categories"], 2)
        self.assertContains(response, "kpi-card")

    def test_gestion_list_visibility_filter(self):
        self.upload(title="Membres doc", visibility=Document.Visibility.MEMBERS)
        self.upload(title="Bureau doc", visibility=Document.Visibility.BUREAU)
        self.client.force_login(self.president)
        response = self.client.get(reverse("documents:manage_list"), {"visibilite": Document.Visibility.BUREAU})
        self.assertContains(response, "Bureau doc")
        self.assertNotContains(response, "Membres doc")

    def test_gestion_list_empty_state_has_upload_cta(self):
        self.client.force_login(self.president)
        response = self.client.get(reverse("documents:manage_list"))
        self.assertContains(response, "Aucun document n’a encore été déposé.")
        self.assertContains(response, reverse("documents:upload"))

    def test_gestion_detail_shows_breadcrumb_and_author(self):
        document = self.upload()
        self.client.force_login(self.president)
        response = self.client.get(reverse("documents:manage_detail", args=[document.pk]))
        self.assertContains(response, "doc-breadcrumb")
        self.assertContains(response, self.president.get_full_name())

    def test_gestion_detail_grant_status_active_and_expired(self):
        document = self.upload()
        services.grant_access(actor=self.president, document=document, user=self.invite,
            expires_at=timezone.now() + timedelta(days=5))
        expired_guest = account("ui-expired-guest@example.invalid", role=Role.INVITE)
        services.grant_access(actor=self.president, document=document, user=expired_guest,
            expires_at=timezone.now() - timedelta(days=1))
        self.client.force_login(self.president)
        response = self.client.get(reverse("documents:manage_detail", args=[document.pk]))
        self.assertContains(response, "Actif")
        self.assertContains(response, "Expiré")

    def test_gestion_detail_no_grants_empty_state(self):
        document = self.upload()
        self.client.force_login(self.president)
        response = self.client.get(reverse("documents:manage_detail", args=[document.pk]))
        self.assertContains(response, "Aucun accès nominatif accordé.")

    def test_gestion_detail_danger_zone_preserved(self):
        document = self.upload()
        self.client.force_login(self.president)
        response = self.client.get(reverse("documents:manage_detail", args=[document.pk]))
        self.assertContains(response, "document-danger-zone")
        self.assertContains(response, "Supprimer le document")
        self.assertContains(response, "data-confirm-delete")
        self.assertContains(response, reverse("documents:manage_delete", args=[document.pk]))

    def test_upload_form_renders_grouped_sections_and_file_drop(self):
        self.client.force_login(self.president)
        response = self.client.get(reverse("documents:upload"))
        self.assertContains(response, "Informations")
        self.assertContains(response, "Classification")
        self.assertContains(response, "Fichier")
        self.assertContains(response, "file-drop")
        self.assertContains(response, "Analyse antivirus automatique")

    def test_upload_scanner_unavailable_shows_inline_error_under_file_field(self):
        self.client.force_login(self.president)
        with patch("apps.documents.services.scan_bytes", side_effect=ScannerUnavailable):
            response = self.client.post(reverse("documents:upload"), {
                "title": "x", "description": "", "category": Document.Category.GENERAL,
                "visibility": Document.Visibility.MEMBERS, "file": pdf(),
            })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "indisponible")
        self.assertFalse(Document.objects.exists())


class UploadSizeLimitTests(TestCase):
    def setUp(self):
        self.president = account("president2@example.invalid", role=Role.PRESIDENT)
        patcher = patch("apps.documents.services.scan_bytes", return_value=ScanResult(clean=True, detail="stream: OK"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_max_bytes_is_fifty_megabytes(self):
        self.assertEqual(services.MAX_BYTES, 50 * 1024 * 1024)

    def test_file_over_old_fifteen_mo_limit_now_accepted(self):
        payload = b"%PDF-1.4\n" + b"0" * (20 * 1024 * 1024)  # 20 Mo : refusé avant, accepté maintenant
        upload = SimpleUploadedFile("gros.pdf", payload, content_type="application/pdf")
        document = services.upload_document(actor=self.president, upload=upload, title="Gros fichier", description="",
            category=Document.Category.GENERAL, visibility=Document.Visibility.MEMBERS)
        self.assertIsNotNone(document.pk)

    def test_file_over_fifty_mo_still_refused(self):
        payload = b"%PDF-1.4\n" + b"0" * (51 * 1024 * 1024)
        upload = SimpleUploadedFile("trop-gros.pdf", payload, content_type="application/pdf")
        with self.assertRaises(ValidationError):
            services.upload_document(actor=self.president, upload=upload, title="Trop gros", description="",
                category=Document.Category.GENERAL, visibility=Document.Visibility.MEMBERS)
