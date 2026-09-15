from io import StringIO
from unittest.mock import patch, MagicMock
from django.test import SimpleTestCase, TestCase, override_settings
from django.core.management import call_command, CommandError
from django.core.exceptions import ValidationError
from apps.documents.scanning import check_scanner, scan_bytes, ScannerUnavailable
from apps.documents.services import upload_document
from apps.documents.tests.test_documents import pdf
from apps.documents.models import Document
from apps.core.tests.test_foundations import account
from apps.governance.models import Role


class HealthTests(SimpleTestCase):
    @patch("apps.documents.management.commands.check_antivirus.check_scanner", return_value="ClamAV synthetic-test")
    def test_command_ok(self, scanner):
        output = StringIO()
        call_command("check_antivirus", stdout=output)
        self.assertIn("disponible", output.getvalue())

    @patch("apps.documents.management.commands.check_antivirus.check_scanner", side_effect=ScannerUnavailable)
    def test_command_unavailable(self, scanner):
        with self.assertRaises(CommandError):
            call_command("check_antivirus")

    @override_settings(CLAMD_SOCKET="/synthetic/socket", CLAMD_HOST=None, CLAMD_PORT=None)
    def test_protocol_health_and_timeout(self):
        sockets = [MagicMock(), MagicMock()]
        sockets[0].__enter__.return_value.recv.return_value = b"PONG\0"
        sockets[1].__enter__.return_value.recv.return_value = b"ClamAV synthetic\0"
        with patch("apps.documents.scanning._connect", side_effect=sockets):
            self.assertEqual(check_scanner(), "ClamAV synthetic")
        with patch("apps.documents.scanning._connect", side_effect=TimeoutError):
            with self.assertRaises(ScannerUnavailable):
                check_scanner()
            with self.assertRaises(ScannerUnavailable):
                scan_bytes(b"synthetic")


class UnexpectedScannerTests(TestCase):
    def test_unexpected_exception_refuses_upload(self):
        actor = account("scanner@example.invalid", role=Role.PRESIDENT)
        with patch("apps.documents.services.scan_bytes", side_effect=RuntimeError("synthetic")):
            with self.assertRaises(ValidationError):
                upload_document(actor=actor, upload=pdf(), title="Test", description="", category="GENERAL", visibility="MEMBERS")
        self.assertFalse(Document.objects.exists())
