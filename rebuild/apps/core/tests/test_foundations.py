from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from io import StringIO
from unittest.mock import patch
import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import connection, connections, IntegrityError, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.core.models import AuditEvent, AuthThrottle
from apps.core.permissions import can, effective_role, CAPABILITIES
from apps.core.throttling import consume
from apps.governance.models import Role, RoleGrant, LionsYear, ClubState
from apps.governance.services import grant_role, revoke_role
from apps.members.models import MemberProfile

User = get_user_model()
PASSWORD = "Synthetic-access-2026!"


def account(email="member@example.invalid", role=Role.MEMBRE, **kwargs):
    user = User.objects.create_user(email, PASSWORD, first_name="Compte", last_name="Synthétique", **kwargs)
    MemberProfile.objects.create(user=user, status="GUEST" if role == Role.INVITE else "ACTIVE")
    if role:
        RoleGrant.objects.create(user=user, role=role, starts_at=timezone.now() - timedelta(hours=1))
    return user


class UserTests(TestCase):
    def test_email_normalized(self):
        user = User.objects.create_user("  Member@Example.INVALID  ", PASSWORD)
        self.assertEqual(user.email, "member@example.invalid")
        self.assertEqual(User.objects.get_by_natural_key(" MEMBER@EXAMPLE.INVALID ").pk, user.pk)

    def test_email_unique(self):
        account()
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user("MEMBER@EXAMPLE.INVALID", PASSWORD)

    def test_database_blocks_unnormalized_bulk_write(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.bulk_create([User(email="OTHER@EXAMPLE.INVALID")])

    def test_empty_email_rejected(self):
        with self.assertRaises(ValueError):
            User.objects.create_user("  ", PASSWORD)

    def test_no_role_or_username_field(self):
        names = {field.name for field in User._meta.fields}
        self.assertNotIn("role", names)
        self.assertNotIn("username", names)

    def test_business_super_is_not_technical(self):
        user = account(role=Role.SUPER_ADMIN)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)
        self.assertTrue(can(user, "account.access_private_area"))

    def test_technical_super_without_grant_has_no_business_access(self):
        user = User.objects.create_superuser("technical@example.invalid", PASSWORD)
        self.assertFalse(can(user, "account.access_private_area"))

    def test_profile_identity_not_duplicated(self):
        names = {field.name for field in MemberProfile._meta.fields}
        self.assertTrue({"id", "user", "status", "created_at", "updated_at"} <= names)
        self.assertFalse({"email", "first_name", "last_name", "role"} & names)


class GrantTests(TestCase):
    def setUp(self):
        self.user = account(role=None)
        self.now = timezone.now()

    def create(self, **kwargs):
        return RoleGrant.objects.create(user=self.user, role=Role.PRESIDENT,
            starts_at=kwargs.pop("starts_at", self.now - timedelta(days=1)), **kwargs)

    def test_active(self):
        self.create()
        self.assertEqual(effective_role(self.user), Role.PRESIDENT)

    def test_future(self):
        self.create(starts_at=self.now + timedelta(days=1))
        self.assertIsNone(effective_role(self.user))

    def test_expired_and_exact_end(self):
        self.create(ends_at=self.now)
        self.assertIsNone(effective_role(self.user, at=self.now))

    def test_revoked(self):
        self.create(revoked_at=self.now)
        self.assertIsNone(effective_role(self.user, at=self.now))

    def test_no_grant(self):
        self.assertIsNone(effective_role(self.user))

    def test_inactive(self):
        self.create()
        self.user.is_active = False
        self.user.save()
        self.assertIsNone(effective_role(self.user))

    def test_unknown_role_constraint(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            RoleGrant.objects.create(user=self.user, role="UNKNOWN", starts_at=self.now)

    def test_dates_constraint(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create(starts_at=self.now, ends_at=self.now)

    def test_overlapping_grants_rejected(self):
        self.create()
        with self.assertRaises(IntegrityError), transaction.atomic():
            RoleGrant.objects.create(user=self.user, role=Role.MEMBRE, starts_at=self.now)

    def test_successive_roles_preserve_history_without_cron(self):
        self.create(ends_at=self.now)
        RoleGrant.objects.create(user=self.user, role=Role.MEMBRE, starts_at=self.now)
        self.assertEqual(effective_role(self.user, at=self.now), Role.MEMBRE)
        self.assertEqual(self.user.role_grants.count(), 2)


class CapabilityTests(TestCase):
    def test_matrix_all_seven_roles(self):
        for role in Role.values:
            with self.subTest(role=role):
                user = account(email=role.lower()+"@example.invalid", role=role)
                for capability in ["account.access_private_area", "account.change_own_password"]:
                    self.assertTrue(can(user, capability))
                for unsupported in ["member_directory.view", "content.publish", "unknown"]:
                    self.assertFalse(can(user, unsupported))

    def test_anonymous_all_denied(self):
        for capability in [*CAPABILITIES, "unknown"]:
            self.assertFalse(can(AnonymousUser(), capability))

    def test_own_object_only(self):
        user, other = account(), account("other@example.invalid")
        self.assertTrue(can(user, "account.change_own_password", obj=user))
        self.assertFalse(can(user, "account.change_own_password", obj=other))
        self.assertFalse(can(user, "account.change_own_password", obj=other.member_profile))

    def test_suspended_or_missing_profile_denied(self):
        user = account()
        MemberProfile.objects.filter(user=user).update(status="SUSPENDED")
        self.assertFalse(can(user, "account.access_private_area"))
        user.member_profile.delete()
        self.assertFalse(can(user, "account.access_private_area"))

    def test_guest_profile_cannot_use_president_grant(self):
        user = account(role=Role.PRESIDENT)
        MemberProfile.objects.filter(user=user).update(status="GUEST")
        self.assertFalse(can(user, "account.access_private_area"))


class YearTests(TestCase):
    def test_empty_state_and_dashboard(self):
        self.client.force_login(account())
        self.assertContains(self.client.get('/espace/'), "Aucune année active définie")
        self.assertEqual(LionsYear.objects.count(), 0)
        self.assertEqual(ClubState.objects.count(), 0)

    def test_active_year(self):
        year = LionsYear.objects.create(starts_on=date(2026, 7, 1), ends_on=date(2027, 7, 1))
        ClubState.objects.create(active_year=year)
        self.client.force_login(account())
        self.assertContains(self.client.get('/espace/'), "2026–2027")

    def test_invalid_dates(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            LionsYear.objects.create(starts_on=date(2026, 7, 1), ends_on=date(2026, 7, 1))

    def test_overlap(self):
        LionsYear.objects.create(starts_on=date(2026, 7, 1), ends_on=date(2027, 7, 1))
        with self.assertRaises(IntegrityError), transaction.atomic():
            LionsYear.objects.create(starts_on=date(2027, 1, 1), ends_on=date(2028, 1, 1))

    def test_adjacent_years_and_singleton(self):
        LionsYear.objects.create(starts_on=date(2026, 7, 1), ends_on=date(2027, 7, 1))
        LionsYear.objects.create(starts_on=date(2027, 7, 1), ends_on=date(2028, 7, 1))
        with self.assertRaises(IntegrityError), transaction.atomic():
            ClubState.objects.create(id=2)


class AuditTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_superuser("operator@example.invalid", PASSWORD)
        self.user = account(role=None)

    def test_grant_and_revoke_traced_without_secrets(self):
        grant = grant_role(actor=self.actor, user=self.user, role=Role.MEMBRE)
        revoke_role(actor=self.actor, grant=grant)
        revoke_role(actor=self.actor, grant=grant)
        self.assertEqual(AuditEvent.objects.count(), 2)
        self.assertEqual(RoleGrant.objects.count(), 1)
        payload = json.dumps(list(AuditEvent.objects.values()), default=str)
        for secret in [PASSWORD, self.actor.password, self.user.email, "token", "SECRET_KEY"]:
            self.assertNotIn(secret, payload)

    def test_business_super_cannot_delegate_technical_privilege(self):
        actor = account("business@example.invalid", Role.SUPER_ADMIN)
        with self.assertRaises(PermissionDenied):
            grant_role(actor=actor, user=self.user, role=Role.SUPER_ADMIN)
        self.assertEqual(AuditEvent.objects.count(), 0)

    def test_audit_failure_rolls_back_grant(self):
        with patch('apps.governance.services.AuditEvent.objects.create', side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                grant_role(actor=self.actor, user=self.user, role=Role.MEMBRE)
        self.assertFalse(RoleGrant.objects.filter(user=self.user).exists())

    def test_bootstrap_command_requires_technical_actor(self):
        call_command('grant_role', actor=str(self.actor.pk), user=str(self.user.pk), role=Role.MEMBRE, stdout=StringIO())
        self.assertTrue(AuditEvent.objects.filter(action="role.granted").exists())
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_superuser)


class AuthTests(TestCase):
    def setUp(self):
        self.user = account()

    def login(self, **extra):
        return self.client.post('/connexion/', {"username": "MEMBER@EXAMPLE.INVALID", "password": PASSWORD, **extra})

    def test_login_email_and_session_rotation(self):
        session = self.client.session
        session['prior'] = True
        session.save()
        old_key = session.session_key
        response = self.login()
        self.assertRedirects(response, '/espace/')
        self.assertNotEqual(self.client.session.session_key, old_key)
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_remember(self):
        self.login(remember="on")
        self.assertFalse(self.client.session.get_expire_at_browser_close())

    def test_invalid_unknown_inactive_same_error(self):
        for email in [self.user.email, 'missing@example.invalid']:
            response = self.client.post('/connexion/', {"username":email, "password":"wrong"})
            self.assertContains(response, "Adresse e-mail ou mot de passe incorrect.")
            self.assertContains(response, email)
            self.assertNotContains(response, 'value="wrong"')
        self.user.is_active=False; self.user.save()
        response = self.login()
        self.assertContains(response, "Adresse e-mail ou mot de passe incorrect.")

    def test_logout_post_not_get(self):
        self.login()
        self.assertEqual(self.client.get('/deconnexion/').status_code, 405)
        self.assertRedirects(self.client.post('/deconnexion/'), '/connexion/')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_csrf_login_reset_logout_change(self):
        client=Client(enforce_csrf_checks=True)
        self.assertEqual(client.post('/connexion/', {'username':self.user.email,'password':PASSWORD}).status_code,403)
        self.assertEqual(client.post('/mot-de-passe-oublie/', {'email':self.user.email}).status_code,403)
        client.force_login(self.user)
        self.assertEqual(client.post('/deconnexion/').status_code,403)
        self.assertEqual(client.post('/espace/mot-de-passe/').status_code,403)

    def test_external_next_rejected(self):
        for url in ['https://evil.invalid/', '//evil.invalid/', 'https://testserver.evil.invalid/', 'javascript:alert(1)']:
            self.client.logout()
            response=self.login(next=url)
            self.assertEqual(response.url,'/espace/')

    def test_local_next(self):
        self.assertEqual(self.login(next='/espace/mot-de-passe/').url,'/espace/mot-de-passe/')

    def test_anonymous_private_url(self):
        self.assertRedirects(self.client.get('/espace/'), '/connexion/?next=/espace/')

    def test_no_grant_refused_even_with_role_query(self):
        self.user.role_grants.update(revoked_at=timezone.now())
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/espace/?role=SUPER_ADMIN').status_code,403)
        self.assertEqual(self.client.get('/espace/mot-de-passe/').status_code,403)

    def test_password_change_updates_only_self_and_preserves_session(self):
        other=account('other@example.invalid')
        self.login()
        response=self.client.post('/espace/mot-de-passe/', {'old_password':PASSWORD,'new_password1':'New-synthetic-access!','new_password2':'New-synthetic-access!','user':str(other.pk)})
        self.assertEqual(response.status_code,302)
        self.user.refresh_from_db(); other.refresh_from_db()
        self.assertTrue(self.user.check_password('New-synthetic-access!'))
        self.assertTrue(other.check_password(PASSWORD))
        self.assertEqual(self.client.get('/espace/').status_code,200)

    def test_login_lockout(self):
        for i in range(5):
            response=self.client.post('/connexion/', {'username':self.user.email,'password':'wrong'})
        self.assertEqual(response.status_code,429)
        self.assertEqual(self.login().status_code,429)

    def test_login_ip_limit_shared_between_accounts(self):
        for i in range(20):
            self.client.post('/connexion/', {'username':f'missing{i}@example.invalid','password':'wrong'})
        self.assertEqual(self.login().status_code,429)

    def test_reset_known_unknown_neutral_and_normalized(self):
        known=self.client.post('/mot-de-passe-oublie/', {'email':'MEMBER@EXAMPLE.INVALID'})
        unknown=self.client.post('/mot-de-passe-oublie/', {'email':'missing@example.invalid'})
        self.assertEqual(known.url,unknown.url)
        self.assertEqual(known.status_code,302)
        self.assertEqual(len(mail.outbox),1)
        self.assertEqual(mail.outbox[0].to,[self.user.email])
        self.assertIn('http://testserver/reinitialiser/', mail.outbox[0].body)
        self.assertTrue(mail.outbox[0].alternatives)

    def test_reset_inactive_no_mail(self):
        self.user.is_active=False;self.user.save()
        self.client.post('/mot-de-passe-oublie/', {'email':self.user.email})
        self.assertEqual(len(mail.outbox),0)

    def test_reset_sender_failure_remains_neutral(self):
        with patch('django.core.mail.EmailMultiAlternatives.send',side_effect=RuntimeError('smtp-private')), self.assertLogs('apps.accounts.forms',level='ERROR') as logs:
            response=self.client.post('/mot-de-passe-oublie/', {'email':self.user.email})
        self.assertEqual(response.status_code,302)
        self.assertNotIn('smtp-private',str(logs.output))

    def test_reset_limits_unknown_addresses(self):
        for i in range(5):
            self.client.post('/mot-de-passe-oublie/', {'email':f'missing{i}@example.invalid'})
        self.assertEqual(self.client.post('/mot-de-passe-oublie/', {'email':self.user.email}).status_code,429)
        stored=json.dumps(list(AuthThrottle.objects.values()),default=str)
        self.assertNotIn(self.user.email,stored)
        self.assertNotIn('127.0.0.1',stored)

    def token_url(self, token=None):
        uid=urlsafe_base64_encode(force_bytes(self.user.pk))
        return reverse('accounts:reset_confirm',kwargs={'uidb64':uid,'token':token or default_token_generator.make_token(self.user)})

    def test_reset_valid_and_token_single_use(self):
        url=self.token_url()
        response=self.client.get(url)
        self.assertEqual(response.status_code,302)
        clean_url=response.url
        self.assertIn('/set-password/',clean_url)
        response=self.client.post(clean_url,{'new_password1':'Changed-synthetic-2026!','new_password2':'Changed-synthetic-2026!'})
        self.assertRedirects(response,reverse('accounts:reset_complete'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Changed-synthetic-2026!'))
        self.assertNotIn('_auth_user_id',self.client.session)
        self.assertContains(self.client.get(url),'Lien indisponible')

    def test_reset_invalid_and_expired(self):
        self.assertContains(self.client.get(self.token_url('invalid-token')),'Lien indisponible')
        with patch.object(default_token_generator,'_now',return_value=default_token_generator._now()-timedelta(hours=2)):
            url=self.token_url()
        self.assertContains(self.client.get(url),'Lien indisponible')

    def test_reset_token_not_in_canonical(self):
        url=self.token_url('invalid-token')
        response=self.client.get(url)
        self.assertContains(response,'rel="canonical" href="http://testserver/mot-de-passe-oublie/"')

    def test_auth_private_noindex_no_cache(self):
        self.client.force_login(self.user)
        for url in ['/connexion/','/mot-de-passe-oublie/','/espace/','/espace/mot-de-passe/']:
            response=self.client.get(url)
            self.assertContains(response,'name="robots" content="noindex, nofollow"')
            self.assertEqual(response['X-Robots-Tag'],'noindex, nofollow')
            self.assertIn('no-store',response['Cache-Control'])

    def test_shell_templates_and_no_future_routes(self):
        response=self.client.get('/')
        self.assertTemplateUsed(response,'base/public.html')
        self.assertContains(response,'District 414 Tunisie')
        self.assertNotContains(response,'District 414-B')
        self.client.force_login(self.user)
        response=self.client.get('/espace/')
        self.assertTemplateUsed(response,'base/private.html')
        self.assertNotContains(response,'?role=')
        self.assertNotContains(response,'data-maquette')
        self.assertNotContains(response,'vote-resultats')
        # Phase B : /espace/votes/ existe désormais (MEMBRE peut consulter ses scrutins).
        self.assertEqual(self.client.get('/espace/votes/').status_code,200)
        self.assertEqual(self.client.get('/espace/audit/').status_code,404)


class ConcurrentTests(TransactionTestCase):
    def test_postgresql_is_real(self):
        self.assertEqual(connection.vendor,'postgresql')
        self.assertTrue(connection.settings_dict['NAME'].startswith('test_lionsmed_rebuild_'))

    def test_simultaneous_grants_one_wins(self):
        actor=User.objects.create_superuser('operator@example.invalid', PASSWORD)
        user=account(role=None)
        def attempt(role):
            try:
                grant_role(actor=actor,user=user,role=role)
                return True
            except (ValidationError,IntegrityError):
                return False
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(attempt,[Role.MEMBRE,Role.PRESIDENT]))
        self.assertEqual(sum(results),1)
        self.assertEqual(RoleGrant.objects.filter(user=user).count(),1)
        self.assertEqual(AuditEvent.objects.count(),1)

    def test_concurrent_throttle_cannot_exceed_limit(self):
        def attempt(i):
            try:
                return consume('test','synthetic',limit=3,seconds=900)
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(attempt,range(6)))
        self.assertEqual(sum(results),3)
        self.assertEqual(AuthThrottle.objects.get().count,3)

    def test_throttle_expiration_without_cron(self):
        self.assertTrue(consume('test','synthetic',limit=1,seconds=10))
        self.assertFalse(consume('test','synthetic',limit=1,seconds=10))
        AuthThrottle.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertTrue(consume('test','synthetic',limit=1,seconds=10))


class IsolationTests(TestCase):
    def test_legacy_tables_refuse_migration(self):
        from django.core.management.base import CommandError
        with patch.object(connection.introspection, "table_names", return_value=["events_event"]):
            with self.assertRaisesMessage(CommandError, "legacy"):
                call_command("migrate", stdout=StringIO())

    def test_self_object_accepts_django_lazy_user_but_not_other_object(self):
        from django.utils.functional import SimpleLazyObject
        user = account()
        lazy_user = SimpleLazyObject(lambda: user)
        self.assertTrue(can(lazy_user, "account.change_own_password", obj=user))
        self.assertFalse(can(lazy_user, "account.change_own_password", obj=account("other@example.invalid")))
