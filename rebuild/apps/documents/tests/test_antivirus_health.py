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
    def test_ping_ok_and_real_synthetic_scan_ok(self):
        ping_socket = MagicMock()
        ping_socket.__enter__.return_value.recv.return_value = b"PONG\0"
        scan_socket = MagicMock()
        scan_socket.__enter__.return_value.recv.return_value = b"stream: OK\0"
        with patch("apps.documents.scanning._connect", side_effect=[ping_socket, scan_socket]) as connect:
            self.assertEqual(check_scanner(), "PING + INSTREAM OK")
        self.assertEqual(connect.call_count, 2)
        sent = b"".join(call.args[0] for call in scan_socket.__enter__.return_value.sendall.call_args_list)
        self.assertIn(b"lionsmed-antivirus-health-check", sent)

    @override_settings(CLAMD_SOCKET="/synthetic/socket", CLAMD_HOST=None, CLAMD_PORT=None)
    def test_ping_failure_is_unavailable(self):
        bad_ping = MagicMock()
        bad_ping.__enter__.return_value.recv.return_value = b"NOPE\0"
        with patch("apps.documents.scanning._connect", return_value=bad_ping):
            with self.assertRaises(ScannerUnavailable):
                check_scanner()

    @override_settings(CLAMD_SOCKET="/synthetic/socket", CLAMD_HOST=None, CLAMD_PORT=None)
    def test_scan_rejection_and_timeout_are_unavailable(self):
        ping = MagicMock()
        ping.__enter__.return_value.recv.return_value = b"PONG\0"
        infected = MagicMock()
        infected.__enter__.return_value.recv.return_value = b"stream: Synthetic FOUND\0"
        with patch("apps.documents.scanning._connect", side_effect=[ping, infected]):
            with self.assertRaises(ScannerUnavailable):
                check_scanner()

        ping = MagicMock()
        ping.__enter__.return_value.recv.return_value = b"PONG\0"
        with patch("apps.documents.scanning._connect", side_effect=[ping, TimeoutError]):
            with self.assertRaises(ScannerUnavailable):
                check_scanner()

    @override_settings(CLAMD_SOCKET="/synthetic/socket", CLAMD_HOST=None, CLAMD_PORT=None)
    def test_connection_timeout_remains_fail_closed(self):
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
