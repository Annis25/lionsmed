import os
import subprocess
from datetime import timedelta
from pathlib import Path
from unittest import skipUnless
from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client
from django.utils import timezone
from apps.core.tests.test_foundations import account
from apps.governance.models import Role, ClubState
from apps.dues.tests.test_dues import lions_year
from apps.satisfaction.services import open_period, submit_satisfaction


@skipUnless(os.environ.get("LIONSMED_FUNCTIONAL_BROWSER") == "1", "Contrôle navigateur fonctionnel opt-in")
class FunctionalBrowserTests(StaticLiveServerTestCase):
    host = "127.0.0.1"

    def test_requested_viewports(self):
        president = account("visual-president@example.invalid", role=Role.PRESIDENT)
        treasurer = account("visual-treasurer@example.invalid", role=Role.TRESORIER)
        member = account("visual-member@example.invalid")
        respondent = account("visual-respondent@example.invalid")
        from tempfile import TemporaryDirectory
        from django.test import override_settings
        from apps.members.tests.test_members import picture
        from apps.members.uploads import encode_photo, photo_storage
        portrait_directory = TemporaryDirectory()
        self.addCleanup(portrait_directory.cleanup)
        portrait_settings = override_settings(PRIVATE_MEDIA_ROOT=portrait_directory.name)
        portrait_settings.enable()
        self.addCleanup(portrait_settings.disable)
        profile = member.member_profile
        profile.photo_key = photo_storage().save("portraits/visual.jpg", encode_photo(picture(size=(240, 400))))
        profile.save()
        period = open_period(actor=president, year=2026, month=9, title="Satisfaction générale", description="Votre avis sur la vie du club", threshold=1,
            opens_at=timezone.now()-timedelta(hours=1), closes_at=timezone.now()+timedelta(days=1), axes="Organisation\nCommunication\nVie du club")
        submit_satisfaction(actor=respondent, period=period, score=4, axis_scores={axis.pk: 4 for axis in period.axes.all()})
        year = lions_year()
        ClubState.objects.update_or_create(pk=1, defaults={"active_year": year})
        from apps.dues.models import DuesSchedule, DuesRecord
        DuesSchedule.objects.create(lions_year=year, tranche1_amount=100, tranche2_amount=150)
        DuesRecord.objects.create(profile=member.member_profile, lions_year=year, tranche1_paid=True)
        sessions = []
        for actor in (president, treasurer, member):
            client = Client()
            client.force_login(actor)
            sessions.append(client.cookies[settings.SESSION_COOKIE_NAME].value)
        env = {**os.environ, "LIONSMED_BROWSER_URL": self.live_server_url, "LIONSMED_VISUAL_COOKIE": settings.SESSION_COOKIE_NAME, "LIONSMED_VISUAL_SESSIONS": ",".join(sessions), "LIONSMED_VISUAL_PERIOD": str(period.pk)}
        result = subprocess.run(["node", str(Path(settings.BASE_DIR)/"tools/browser_functional.cjs")], env=env, capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        print(result.stdout.strip())
