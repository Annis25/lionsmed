import os
import secrets
import subprocess
from pathlib import Path
from unittest import skipUnless
from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from .test_foundations import account


@skipUnless(os.environ.get('LIONSMED_BROWSER_TESTS') == '1', 'Activer les contrôles navigateur selon docs/LOT_1_FONDATIONS.md')
class BrowserTests(StaticLiveServerTestCase):
    host = '127.0.0.1'

    def test_responsive_and_keyboard(self):
        user=account('browser@example.invalid')
        password=secrets.token_urlsafe(24)
        user.set_password(password);user.save()
        env={**os.environ,'LIONSMED_BROWSER_URL':self.live_server_url,
             'LIONSMED_BROWSER_EMAIL':user.email,'LIONSMED_BROWSER_PASSWORD':password}
        result=subprocess.run(['node',str(Path(settings.BASE_DIR)/'tools/browser.cjs')],env=env,capture_output=True,text=True,timeout=180)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        print(result.stdout.strip())
