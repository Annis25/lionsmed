from io import BytesIO
from unittest.mock import patch
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from apps.core.tests.test_foundations import account
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

    def test_list_detail_head_download_share_the_same_acl(self):
        document = self.upload(Document.Visibility.RESPONSABLES)
        self.client.force_login(self.member)
        list_response = self.client.get(reverse("documents:list"))
        self.assertNotContains(list_response, document.title)
        self.assertEqual(self.client.get(reverse("documents:detail", args=[document.pk])).status_code, 404)
        self.assertEqual(self.client.head(reverse("documents:download", args=[document.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("documents:download", args=[document.pk])).status_code, 404)
        self.client.force_login(self.president)
        self.assertContains(self.client.get(reverse("documents:list")), document.title)
        self.assertEqual(self.client.get(reverse("documents:detail", args=[document.pk])).status_code, 200)
        self.assertEqual(self.client.head(reverse("documents:download", args=[document.pk])).status_code, 200)
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
