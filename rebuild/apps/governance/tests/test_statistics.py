from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.tests.test_foundations import account
from apps.documents.scanning import ScanResult
from apps.documents.services import upload_document
from apps.documents.tests.test_documents import pdf
from apps.governance.models import Role


class StatisticsDisplayTests(TestCase):
    def test_document_categories_are_shown_with_their_label(self):
        president = account("president-statistics@example.invalid", role=Role.PRESIDENT)
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        with override_settings(PRIVATE_MEDIA_ROOT=Path(media.name)), patch("apps.documents.services.scan_bytes", return_value=ScanResult(True)):
            upload_document(actor=president, upload=pdf(), title="Compte rendu", description="", category="GENERAL", visibility="MEMBERS")
            upload_document(actor=president, upload=pdf(), title="Circulaire", description="", category="DISTRICT", visibility="MEMBERS")
        self.client.force_login(president)
        response = self.client.get(reverse("governance:statistics"))
        self.assertContains(response, "Général — 1")
        self.assertContains(response, "District — 1")
        for code in ("GENERAL", "DISTRICT"):
            self.assertNotContains(response, code)
