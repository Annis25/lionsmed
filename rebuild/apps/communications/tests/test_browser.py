import os
import secrets
import subprocess
from pathlib import Path
from unittest import skipUnless
from uuid import uuid4

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.tests.test_foundations import account
from apps.governance.models import Role

from ..models import MemberEmailCampaign, OutboxMessage
from ..services import queue_member_broadcast

MEMBERS = [
    ("Anis", "Besbes", "anis.besbes", Role.MEMBRE), ("Rania", "Trabelsi", "rania.trabelsi", Role.MEMBRE),
    ("Ahmed", "Ben Ali", "ahmed.benali", Role.SECRETAIRE), ("Sana", "Gargouri", "sana.gargouri", Role.TRESORIER),
    ("Mohamed-Amine", "Ben Abdallah-Chaabouni", "mohamed.amine.benabdallah.chaabouni", Role.MEMBRE),
    ("Leïla", "Fourati", "leila.fourati", Role.VICE_PRESIDENT), ("Karim", "Jarraya", "karim.jarraya", Role.MEMBRE),
    ("Ines", "Kammoun", "ines.kammoun", Role.MEMBRE), ("Hatem", "Masmoudi", "hatem.masmoudi", Role.GMT),
    ("Nadia", "Sellami", "nadia.sellami", Role.MEMBRE), ("Slim", "Turki", "slim.turki", Role.MEMBRE),
    ("Yosra", "Zghal", "yosra.zghal", Role.MEMBRE),
]


@skipUnless(os.environ.get("LIONSMED_BROWSER_TESTS") == "1", "Activer LIONSMED_BROWSER_TESTS")
class CommunicationBrowserTests(StaticLiveServerTestCase):
    host = "127.0.0.1"

    def test_communication_pages(self):
        president = account("browser-communication@example.invalid", role=Role.PRESIDENT)
        president.first_name, president.last_name = "Test", "Président"
        password = secrets.token_urlsafe(24)
        president.set_password(password)
        president.save()
        members = {}
        for first_name, last_name, local, role in MEMBERS:
            user = account(f"{local}@example.invalid", role=role)
            user.first_name, user.last_name = first_name, last_name
            user.save(update_fields=["first_name", "last_name"])
            members[local] = user
        account("invite-communication@example.invalid", role=Role.INVITE)

        def campaign(subject, selected, external=()):
            return queue_member_broadcast(actor=president, subject=subject, body="Bonjour à tous,\n\nMessage synthétique de recette.",
                idempotency_key=uuid4(), member_ids=[user.pk for user in selected], extra_emails=list(external))[0]

        def state(item, recipient, **values):
            OutboxMessage.objects.filter(object_id=item.pk, recipient=recipient).update(**values)

        done = campaign("Réunion mensuelle", members.values())
        OutboxMessage.objects.filter(object_id=done.pk).update(state="SENT", attempts=1, sent_at=timezone.now())
        mixed = campaign("Assemblée générale ordinaire et renouvellement du bureau",
                         [members["anis.besbes"], members["rania.trabelsi"], members["ahmed.benali"], members["sana.gargouri"],
                          members["mohamed.amine.benabdallah.chaabouni"]], ["contact@association.example", "partenaire@example.invalid"])
        for local in ("anis.besbes", "ahmed.benali", "mohamed.amine.benabdallah.chaabouni"):
            state(mixed, members[local].email, state="SENT", attempts=1, sent_at=timezone.now())
        state(mixed, "contact@association.example", state="FAILED", attempts=5, error_code="recipient_refused")
        state(mixed, members["sana.gargouri"].email, state="FAILED", attempts=1, error_code="not_applicable")
        state(mixed, "partenaire@example.invalid", state="PENDING", attempts=2, error_code="delivery_failed")
        failed = campaign("Invitation aux partenaires", [], ["partenaire@example.invalid", "mairie@example.invalid"])
        OutboxMessage.objects.filter(object_id=failed.pk).update(state="FAILED", attempts=5, error_code="delivery_failed")

        env = {**os.environ, "LIONSMED_BROWSER_URL": self.live_server_url, "LIONSMED_BROWSER_EMAIL": president.email,
               "LIONSMED_BROWSER_PASSWORD": password,
               "LIONSMED_CAMPAIGN_PATH": reverse("communications:broadcast_detail", args=[mixed.pk]),
               "LIONSMED_FAILED_PATH": reverse("communications:broadcast_detail", args=[failed.pk]),
               "LIONSMED_CAMPAIGN_COUNT": str(MemberEmailCampaign.objects.count())}
        result = subprocess.run(["node", str(Path(settings.BASE_DIR) / "tools/browser_communication.cjs")],
                                env=env, capture_output=True, text=True, timeout=600)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout.strip())
