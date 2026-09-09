import os
import secrets
import subprocess
from datetime import date
from pathlib import Path
from unittest import skipUnless
from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from apps.core.tests.test_foundations import account
from apps.governance.models import Role, LionsYear, Mandate
from apps.members.models import MemberProfile, AssociationExperience

@skipUnless(os.environ.get('LIONSMED_BROWSER_TESTS') == '1', 'Activer LIONSMED_BROWSER_TESTS')
class MemberBrowserTests(StaticLiveServerTestCase):
    host = '127.0.0.1'
    def test_lot2_pages(self):
        user=account('browser-lot2@example.invalid',role=Role.PRESIDENT)
        password=secrets.token_urlsafe(24);user.set_password(password);user.save()
        other=account('portrait-test@example.invalid')
        other.first_name='Autre';other.last_name='Membre synthétique';other.save()
        MemberProfile.objects.filter(user=other).update(directory_visible=True,share_profession=True,profession='Profession synthétique')
        year=LionsYear.objects.create(starts_on=date(2020,1,1),ends_on=date(2021,1,1))
        Mandate.objects.create(profile=user.member_profile,function='Fonction historique synthétique',lions_year=year,starts_on=year.starts_on,ends_on=year.ends_on)
        exp=AssociationExperience.objects.create(profile=user.member_profile,network='LEO',club='Club synthétique',function='Service associatif',starts_on=date(2018,1,1),ends_on=date(2019,1,1))
        env={**os.environ,'LIONSMED_BROWSER_URL':self.live_server_url,'LIONSMED_BROWSER_EMAIL':user.email,'LIONSMED_BROWSER_PASSWORD':password,'LIONSMED_OTHER_ID':str(other.pk),'LIONSMED_EXPERIENCE_ID':str(exp.pk)}
        result=subprocess.run(['node',str(Path(settings.BASE_DIR)/'tools/browser_members.cjs')],env=env,capture_output=True,text=True,timeout=180)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        print(result.stdout.strip())
