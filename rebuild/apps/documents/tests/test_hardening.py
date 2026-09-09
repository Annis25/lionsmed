import socket
import struct
import threading
import zipfile
from io import BytesIO
from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from apps.core.tests.test_foundations import account
from apps.core.models import AuditEvent
from apps.governance.models import Role
from .. import services
from ..models import Document
from ..scanning import scan_bytes, ScannerUnavailable
from ..office_validation import validate_structure, validate_office_zip, validate_pdf


def pdf(name="doc.pdf", body=b"%PDF-1.4 synthetic"):
    return SimpleUploadedFile(name, body, content_type="application/pdf")


def docx(entries, name="doc.docx"):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for filename, content in entries.items():
            archive.writestr(filename, content)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


class FakeClamd:
    """Petit serveur TCP qui parle le protocole INSTREAM pour tester scan_bytes réellement,
    sans dépendre d'une installation ClamAV locale."""
    def __init__(self, verdict=b"stream: OK\0"):
        self.verdict = verdict
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(1)
        self.port = self.server.getsockname()[1]
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        try:
            conn, _ = self.server.accept()
        except OSError:
            return
        with conn:
            conn.recv(len(b"zINSTREAM\0"))
            while True:
                header = conn.recv(4)
                if len(header) < 4:
                    break
                length = struct.unpack("!L", header)[0]
                if length == 0:
                    break
                remaining = length
                while remaining:
                    remaining -= len(conn.recv(remaining))
            conn.sendall(self.verdict)

    def close(self):
        self.server.close()


class ScanningProtocolTests(TestCase):
    def test_unconfigured_scanner_is_unavailable(self):
        with self.assertRaises(ScannerUnavailable):
            scan_bytes(b"data")

    def test_clean_verdict_over_real_socket(self):
        fake = FakeClamd(verdict=b"stream: OK\0")
        try:
            result = scan_bytes(b"hello world", host="127.0.0.1", port=fake.port)
            self.assertTrue(result.clean)
        finally:
            fake.close()

    def test_infected_verdict_over_real_socket(self):
        fake = FakeClamd(verdict=b"stream: Eicar-Test-Signature FOUND\0")
        try:
            result = scan_bytes(b"malicious", host="127.0.0.1", port=fake.port)
            self.assertFalse(result.clean)
        finally:
            fake.close()

    def test_unreachable_host_is_unavailable(self):
        with self.assertRaises(ScannerUnavailable):
            scan_bytes(b"data", host="127.0.0.1", port=1, timeout=1)


class UploadFailsClosedTests(TestCase):
    def setUp(self):
        self.president = account("president@example.invalid", role=Role.PRESIDENT)

    def test_scanner_unavailable_blocks_upload(self):
        with self.assertRaises(ValidationError):
            services.upload_document(actor=self.president, upload=pdf(), title="x", description="",
                category=Document.Category.GENERAL, visibility=Document.Visibility.MEMBERS)
        self.assertEqual(Document.objects.count(), 0)

    @patch("apps.documents.services.scan_bytes")
    def test_infected_document_is_rejected_and_audited(self, scan):
        from ..scanning import ScanResult
        scan.return_value = ScanResult(clean=False, detail="stream: Eicar FOUND")
        with self.assertRaises(ValidationError):
            services.upload_document(actor=self.president, upload=pdf(), title="x", description="",
                category=Document.Category.GENERAL, visibility=Document.Visibility.MEMBERS)
        self.assertEqual(Document.objects.count(), 0)
        self.assertTrue(AuditEvent.objects.filter(action="document.upload_rejected_infected").exists())


class StructuralValidationTests(TestCase):
    def test_pdf_signature_mismatch_rejected(self):
        with self.assertRaises(ValidationError):
            validate_pdf(b"not a pdf at all")

    def test_pdf_with_javascript_rejected(self):
        with self.assertRaises(ValidationError):
            validate_pdf(b"%PDF-1.4 ... /JavaScript (evil) ...")

    def test_docx_without_required_entry_rejected(self):
        upload = docx({"other.xml": "<x/>"})
        with self.assertRaises(ValidationError):
            validate_office_zip(upload.read(), ".docx")

    def test_docx_with_macro_rejected(self):
        upload = docx({"word/document.xml": "<x/>", "word/vbaProject.bin": "macro"})
        with self.assertRaises(ValidationError):
            validate_office_zip(upload.read(), ".docx")

    def test_docx_path_traversal_rejected(self):
        upload = docx({"word/document.xml": "<x/>", "../../etc/passwd": "x"})
        with self.assertRaises(ValidationError):
            validate_office_zip(upload.read(), ".docx")

    def test_valid_docx_passes(self):
        upload = docx({"word/document.xml": "<x/>", "[Content_Types].xml": "<t/>"})
        validate_office_zip(upload.read(), ".docx")  # ne lève pas

    def test_validate_structure_dispatches_by_suffix(self):
        validate_structure(b"%PDF-1.4 clean", ".pdf")  # ne lève pas
        with self.assertRaises(ValidationError):
            validate_structure(b"\xff\xd8\xff not really a jpeg signature mismatch", ".pdf")

    def test_zip_bomb_ratio_rejected(self):
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("word/document.xml", b"0" * (5 * 1024 * 1024))
        raw = buffer.getvalue()
        with self.assertRaises(ValidationError):
            validate_office_zip(raw, ".docx")
