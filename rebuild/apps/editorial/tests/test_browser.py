import os
import secrets
import subprocess
from pathlib import Path
from unittest import skipUnless
from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from apps.core.tests.test_foundations import account
from apps.governance.models import Role
from .test_public import content
from apps.editorial.publication import publish_content

@skipUnless(os.environ.get('LIONSMED_BROWSER_TESTS')=='1','Activer LIONSMED_BROWSER_TESTS')
class PublicBrowserTests(StaticLiveServerTestCase):
    host='127.0.0.1'
    def test_public_responsive(self):
        actor=account('browser-public@example.invalid',role=Role.PRESIDENT)
        password=secrets.token_urlsafe(24);actor.set_password(password);actor.save()
        for kind in ['action','event']:publish_content(actor=actor,obj=content(actor,kind),kind=kind)
        env={**os.environ,'LIONSMED_BROWSER_URL':self.live_server_url,'LIONSMED_BROWSER_EMAIL':actor.email,'LIONSMED_BROWSER_PASSWORD':password}
        result=subprocess.run(['node',str(Path(settings.BASE_DIR)/'tools/browser_public.cjs')],env=env,capture_output=True,text=True,timeout=180)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        print(result.stdout.strip())
