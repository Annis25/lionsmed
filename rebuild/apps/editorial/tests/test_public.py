import json
import re
import tempfile
from datetime import timedelta
from io import BytesIO
from uuid import uuid4
from unittest.mock import patch
from PIL import Image
from django.contrib.auth import get_user_model
from django.core import signing, mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, Client, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from apps.core.tests.test_foundations import account
from apps.core.models import AuditEvent, AuthThrottle
from apps.core.permissions import can
from apps.governance.models import Role
from apps.service_actions.models import Action, Axis
from apps.service_actions.forms import ActionForm
from apps.agenda.models import Event
from apps.editorial.models import Redirect, EditorialSection, ImpactMetric
from apps.editorial.publication import save_content, publish_content, withdraw_content
from apps.editorial.images import upload_image
from apps.communications.models import ContactRequest, OutboxMessage
from apps.communications.forms import ApplicationForm, ContactForm
from apps.communications.services import submit, change_state
from apps.communications.outbox import deliver_batch
from apps.members.models import MembershipApplication


def content(user, kind='action', slug='synthetic', **kwargs):
    data=dict(title='Contenu synthétique',slug=slug,summary='Résumé synthétique',body='Récit synthétique',created_by=user,updated_by=user)
    if kind=='action':data.update(axis='DIABETE',performed_on=timezone.localdate(),location='Lieu synthétique')
    if kind=='event':data.update(starts_at=timezone.now()+timedelta(days=1),ends_at=timezone.now()+timedelta(days=1,hours=2),location='Lieu synthétique',visibility='PUBLIC')
    data.update(kwargs)
    return {'action':Action,'event':Event}[kind].objects.create(**data)


def submission(kind='application', **changes):
    data=dict(email='synthetic@example.invalid',submission_token=signing.dumps({'id':str(uuid4()),'kind':kind},salt='public-submission'))
    data.update(dict(first_name='Prénom',last_name='Nom',phone='+21620000000',motivation='Motivation synthétique',consent='on') if kind=='application' else dict(name='Nom synthétique',subject='GENERAL',message='Message synthétique'))
    data.update(changes)
    return data

class PublicationTests(TestCase):
    def setUp(self):self.actor=account(role=Role.PRESIDENT)
    def test_drafts_and_publication_all_domains(self):
        for kind in ['action','event']:
            with self.subTest(kind=kind):
                obj=content(self.actor,kind)
                self.assertEqual(self.client.get(obj.get_absolute_url()).status_code,404)
                obj=publish_content(actor=self.actor,obj=obj,kind=kind)
                self.assertEqual(self.client.get(obj.get_absolute_url()).status_code,200)
                self.assertTrue(obj.meta_title);self.assertTrue(obj.meta_description)
                withdraw_content(actor=self.actor,obj=obj,kind=kind)
                self.assertEqual(self.client.get(obj.get_absolute_url()).status_code,404)
        self.assertEqual(AuditEvent.objects.filter(action__endswith='.published').count(),2)
    def test_action_axes_include_all_and_the_four_priorities(self):self.assertEqual(set(Axis.values),{'TOUT','DIABETE','ENVIRONNEMENT','HUMANITAIRE','JEUNESSE'})
    def test_invalid_publication_data(self):
        for changes in [dict(performed_on=timezone.localdate()+timedelta(days=1)),dict(location='')]:
            obj=content(self.actor,slug=str(uuid4()),**changes)
            with self.assertRaises(ValidationError):publish_content(actor=self.actor,obj=obj,kind='action')
        obj=content(self.actor,'event',location='')
        with self.assertRaises(ValidationError):publish_content(actor=self.actor,obj=obj,kind='event')
        # Lot présences/calendrier privé : un événement PRIVATE se publie aussi (calendrier interne),
        # sans jamais apparaître dans EventQuerySet.public() qui reste filtré sur PUBLIC.
        private_obj=content(self.actor,'event',slug=str(uuid4()),visibility='PRIVATE')
        published=publish_content(actor=self.actor,obj=private_obj,kind='event')
        self.assertEqual(published.status,'PUBLISHED')
        self.assertFalse(Event.objects.public().filter(pk=published.pk).exists())
    def test_optional_action_fields(self):
        obj=publish_content(actor=self.actor,obj=content(self.actor),kind='action')
        response=self.client.get(obj.get_absolute_url())
        self.assertNotContains(response,'Bénéficiaires');self.assertIsNone(obj.cover);self.assertIsNone(obj.beneficiaries)
    def test_action_form_accepts_only_instagram_links(self):
        data=dict(title='Action Instagram',axis='DIABETE',summary='Résumé',body='Récit',performed_on=str(timezone.localdate()),location='Lieu',instagram_url='https://www.instagram.com/p/exemple/')
        self.assertTrue(ActionForm(data,actor=self.actor).is_valid())
        data['instagram_url']='https://example.invalid/publication'
        form=ActionForm(data,actor=self.actor)
        self.assertFalse(form.is_valid())
        self.assertIn('instagram_url',form.errors)
    def test_slug_stays_stable_when_an_action_is_edited(self):
        obj=content(self.actor)
        def edit(slug,title='Titre changé'):
            nonlocal obj
            data=dict(title=title,slug=slug,axis='DIABETE',summary='Résumé',body='Récit',performed_on=str(timezone.localdate()),location='Lieu')
            form=ActionForm(data,actor=self.actor,instance=obj)
            self.assertTrue(form.is_valid(),form.errors)
            obj=save_content(actor=self.actor,form=form,kind='action')
            return publish_content(actor=self.actor,obj=obj,kind='action')
        edit(obj.slug);self.assertEqual(obj.slug,'synthetic')
        edit('second');edit('third')
        self.assertEqual(self.client.get('/nos-actions/synthetic/').status_code,200)
        self.assertFalse(Redirect.objects.exists())
    def test_slug_generation_collision_and_edit_withdrawal(self):
        data=dict(title='Titre nouveau',axis='DIABETE',summary='Résumé',body='Récit',performed_on=str(timezone.localdate()),location='Lieu')
        form=ActionForm(data,actor=self.actor);self.assertTrue(form.is_valid(),form.errors)
        obj=save_content(actor=self.actor,form=form,kind='action');self.assertEqual(obj.slug,'titre-nouveau')
        form=ActionForm(data,actor=self.actor)
        with self.assertRaises(ValidationError):save_content(actor=self.actor,form=form,kind='action')
        obj=publish_content(actor=self.actor,obj=obj,kind='action')
        form=ActionForm({**data,'slug':obj.slug},actor=self.actor,instance=obj)
        obj=save_content(actor=self.actor,form=form,kind='action');self.assertEqual(obj.status,'DRAFT')
    def test_redirect_rejects_external_loops_and_chains(self):
        for path in ['https://evil.invalid/','//evil.invalid/','/%2f%2fevil.invalid/','/bad\\path/','/a?x=1','/a#fragment','/a\n']:
            with self.assertRaises(ValidationError):Redirect(old_path='/old/',new_path=path).full_clean()
        with self.assertRaises(ValidationError):Redirect(old_path='/a/',new_path='/a/').full_clean()
        Redirect.objects.create(old_path='/a/',new_path='/b/')
        with self.assertRaises(ValidationError):Redirect(old_path='/c/',new_path='/a/').full_clean()
    def test_public_filters_pagination_and_archives(self):
        for i in range(11):publish_content(actor=self.actor,obj=content(self.actor,slug=f'action-{i}',axis='JEUNESSE' if i==0 else 'DIABETE'),kind='action')
        r=self.client.get('/nos-actions/');self.assertEqual(len(r.context['page_obj']),9)
        self.assertEqual(len(self.client.get('/nos-actions/?page=2').context['page_obj']),2)
        self.assertEqual(len(self.client.get('/nos-actions/?axis=JEUNESSE').context['page_obj']),1)
        self.assertEqual(self.client.get('/actualites/').status_code,404)
        self.assertEqual(self.client.get('/actualites/inconnu/').status_code,404)
        past=content(self.actor,'event',starts_at=timezone.now()-timedelta(days=2),ends_at=timezone.now()-timedelta(days=1))
        publish_content(actor=self.actor,obj=past,kind='event')
        self.assertEqual(len(self.client.get('/evenements/').context['page_obj']),0)
        self.assertEqual(len(self.client.get('/evenements/?archive=1').context['page_obj']),1)
    def test_permission_matrix_http_and_service(self):
        for role in Role.values:
            user=account(email=role+'@example.invalid',role=role);self.client.force_login(user)
            allowed=role in {Role.SUPER_ADMIN,Role.PRESIDENT,Role.PRESIDENT_FONDATEUR,Role.SECRETAIRE}
            for kind in ['action','event']:
                self.assertEqual(self.client.get(reverse('editorial_management:add',kwargs={'kind':kind})).status_code,200 if allowed else 403)
                obj=content(self.actor,kind,slug=str(uuid4()))
                if allowed:publish_content(actor=user,obj=obj,kind=kind)
                else:
                    with self.assertRaises(PermissionDenied):publish_content(actor=user,obj=obj,kind=kind)
            for kind, allowed_roles in [
                ('application', {Role.PRESIDENT, Role.GMT}),
                ('contact', {Role.PRESIDENT, Role.SECRETAIRE}),
            ]:
                request_access = role in allowed_roles
                self.assertEqual(self.client.get(reverse('communications:inbox',kwargs={'kind':kind})).status_code,200 if request_access else 403)
                self.assertEqual(can(user,kind+'.view'), request_access)
                self.assertEqual(can(user,kind+'.manage'), request_access)
        self.client.logout()
        self.assertEqual(self.client.get('/espace/contenu/').status_code,302)
    def test_management_post_and_csrf(self):
        self.client.force_login(self.actor)
        url=reverse('editorial_management:add',kwargs={'kind':'action'})
        response=self.client.post(url,dict(title='Vraie saisie test',axis='DIABETE',summary='Résumé',body='Texte',performed_on=str(timezone.localdate()),location='Lieu'))
        self.assertEqual(response.status_code,302)
        obj=Action.objects.get(title='Vraie saisie test')
        url=reverse('editorial_management:publish',kwargs={'kind':'action','object_id':obj.pk})
        self.assertEqual(self.client.get(url).status_code,405)
        strict=Client(enforce_csrf_checks=True);strict.force_login(self.actor)
        self.assertEqual(strict.post(url).status_code,403)
        self.assertEqual(self.client.post(url).status_code,302)
        obj.refresh_from_db();self.assertEqual(obj.status,'PUBLISHED')

@override_settings(PUBLIC_INDEXING_ENABLED=True,SITE_ORIGIN='https://canonical.example.invalid')
class SeoTests(TestCase):
    def setUp(self):self.actor=account(role=Role.SECRETAIRE)
    def test_all_empty_pages_metadata(self):
        titles=[]
        for path in ['/','/notre-club/','/nos-actions/','/rejoindre/','/candidature/','/contact/','/mentions-legales/','/confidentialite/','/plan-du-site/']:
            r=self.client.get(path);self.assertEqual(r.status_code,200,path);html=r.content.decode()
            self.assertEqual(len(re.findall(r'<h1[ >]',html)),1,path)
            self.assertIn('name="description"',html);self.assertIn('property="og:title"',html)
            self.assertIn('https://canonical.example.invalid'+path,html)
            titles.append(re.search(r'<title>(.*?)</title>',html,re.S).group(1))
            for raw in re.findall(r'<script type="application/ld\+json">(.*?)</script>',html,re.S):json.loads(raw)
        self.assertEqual(len(titles),len(set(titles)))
        html=self.client.get('/').content.decode();self.assertNotIn('aucune actualité',html.lower());self.assertNotIn('414-B',html)
    def test_indexing_policy_sitemap_and_robots(self):
        action=publish_content(actor=self.actor,obj=content(self.actor),kind='action')
        draft=content(self.actor,slug='secret-draft')
        for path in ['/candidature/','/connexion/','/nos-actions/?axis=DIABETE','/mentions-legales/']:
            self.assertIn('noindex',self.client.get(path)['X-Robots-Tag'])
        self.assertIn('index',self.client.get('/')['X-Robots-Tag'])
        sitemap=self.client.get('/sitemap.xml');self.assertContains(sitemap,action.get_absolute_url());self.assertNotContains(sitemap,draft.slug)
        self.assertNotContains(sitemap,'/candidature/');self.assertNotContains(sitemap,'/espace/');self.assertContains(sitemap,'<lastmod>')
        self.assertContains(self.client.get('/robots.txt'),'Allow: /')
        with override_settings(PUBLIC_INDEXING_ENABLED=False):
            self.assertIn('noindex',self.client.get('/')['X-Robots-Tag']);self.assertNotContains(self.client.get('/sitemap.xml'),'<url>');self.assertContains(self.client.get('/robots.txt'),'Disallow: /')
    def test_schema_types_and_script_escaping(self):
        for kind,expected in [('action',None),('event','Event')]:
            obj=content(self.actor,kind,title='Test </script><script>alert(1)</script>')
            publish_content(actor=self.actor,obj=obj,kind=kind)
            html=self.client.get(obj.get_absolute_url()).content.decode()
            raw=re.search(r'<script type="application/ld\+json">(.*?)</script>',html,re.S).group(1)
            types=[x['@type'] for x in json.loads(raw)['@graph']]
            if expected:self.assertIn(expected,types)
            else:self.assertNotIn('Event',types)
            self.assertNotIn('<script>alert(1)</script>',html)
    def test_query_count_constant_no_private_queries(self):
        def count():
            with CaptureQueriesContext(connection) as queries:self.client.get('/nos-actions/')
            self.assertFalse(any('governance_rolegrant' in q['sql'] for q in queries))
            return len(queries)
        publish_content(actor=self.actor,obj=content(self.actor),kind='action');small=count()
        for i in range(8):publish_content(actor=self.actor,obj=content(self.actor,slug=f'item-{i}'),kind='action')
        self.assertEqual(count(),small)

class PublicImageTests(TestCase):
    def test_action_form_uploads_the_main_image_and_renders_it_publicly(self):
        actor=account(role=Role.PRESIDENT);self.client.force_login(actor)
        buf=BytesIO();Image.new('RGB',(1200,600),'blue').save(buf,'JPEG')
        photo=SimpleUploadedFile('action.jpg',buf.getvalue(),content_type='image/jpeg')
        with tempfile.TemporaryDirectory() as root,override_settings(PUBLIC_IMAGE_ROOT=root):
            response=self.client.post(reverse('editorial_management:add',kwargs={'kind':'action'}),{
                'title':'Action avec image','axis':'DIABETE','summary':'Résumé','body':'Récit',
                'performed_on':str(timezone.localdate()),'location':'Lieu','main_image_upload':photo,'intent':'publish',
            })
            self.assertEqual(response.status_code,302)
            obj=Action.objects.get(title='Action avec image')
            self.assertIsNotNone(obj.cover)
            self.assertEqual(obj.status,'PUBLISHED')
            self.assertContains(self.client.get('/nos-actions/'),obj.cover.get_absolute_url())
            self.assertContains(self.client.get(obj.get_absolute_url()),obj.cover.get_absolute_url())

    def test_approval_derivatives_and_public_boundary(self):
        actor=account(role=Role.PRESIDENT)
        def photo():
            buf=BytesIO();Image.new('RGB',(1200,600),'blue').save(buf,'JPEG')
            return SimpleUploadedFile('test.jpg',buf.getvalue(),content_type='image/jpeg')
        with tempfile.TemporaryDirectory() as root,override_settings(PUBLIC_IMAGE_ROOT=root):
            with self.assertRaises(ValidationError):upload_image(actor=actor,upload=photo(),alt='Test',source='Source synthétique',approved=False)
            item=upload_image(actor=actor,upload=photo(),alt='Test',source='Source synthétique',approved=True)
            self.assertEqual(item.width,1024);self.assertEqual(self.client.get(item.get_absolute_url()).status_code,404)
            obj=publish_content(actor=actor,obj=content(actor,cover=item),kind='action')
            response=self.client.get(item.get_absolute_url());self.assertEqual(response.status_code,200);self.assertEqual(response['Content-Type'],'image/webp');b"".join(response.streaming_content)
            withdraw_content(actor=actor,obj=obj,kind='action');self.assertEqual(self.client.get(item.get_absolute_url()).status_code,404)

class SubmissionTests(TestCase):
    def test_prg_idempotence_no_user(self):
        before=get_user_model().objects.count()
        for kind,path,Model in [('application','/candidature/',MembershipApplication),('contact','/contact/',ContactRequest)]:
            data=submission(kind)
            with override_settings(CONTACT_RECIPIENT='internal@example.invalid'):
                r=self.client.post(path,data);self.assertEqual(r.status_code,302)
                self.assertEqual(self.client.post(path,data).status_code,302)
            self.assertEqual(Model.objects.count(),1)
        self.assertEqual(get_user_model().objects.count(),before);self.assertEqual(OutboxMessage.objects.count(),2)
    def test_validation_spam_and_accessible_errors(self):
        for kind,Form in [('application',ApplicationForm),('contact',ContactForm)]:
            field='motivation' if kind=='application' else 'message'
            for changes in [dict(email='bad'),dict(email='a@example.invalid\nBcc:x@example.invalid'),{field:'x'*5001},dict(website='spam'),dict(submission_token='tampered')]:
                self.assertFalse(Form(submission(kind,**changes)).is_valid(),changes.keys())
            data=submission(kind)
            with patch('django.core.signing.time.time',return_value=timezone.now().timestamp()+4000):self.assertFalse(Form(data).is_valid())
        response=self.client.post('/candidature/',submission(first_name=''));self.assertContains(response,'aria-invalid="true"')
    def test_application_phone_required_server_side(self):
        self.assertFalse(ApplicationForm(submission('application',phone='')).is_valid())
        self.assertTrue(ApplicationForm(submission('application')).is_valid())
        response=self.client.post('/candidature/',submission('application',phone=''))
        self.assertContains(response,'obligatoire')
        self.assertEqual(MembershipApplication.objects.count(),0)
    def test_csrf_and_limits(self):
        for path,kind in [('/candidature/','application'),('/contact/','contact')]:
            self.assertEqual(Client(enforce_csrf_checks=True).post(path,submission(kind)).status_code,403)
            for i in range(5):self.client.post(path,submission(kind,email=f'user{i}@example.invalid'))
            self.assertEqual(self.client.post(path,submission(kind)).status_code,429)
    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_smtp_failure_retry_and_receipt_only(self):
        obj=submit(ApplicationForm(submission()))
        with patch('apps.communications.outbox.EmailMultiAlternatives.send',side_effect=OSError('sensitive SMTP detail')):
            self.assertEqual(deliver_batch()['failed'],1)
        self.assertTrue(MembershipApplication.objects.filter(pk=obj.pk).exists())
        out=OutboxMessage.objects.get();self.assertEqual(out.state,'PENDING');self.assertEqual(out.error_code,'delivery_failed')
        OutboxMessage.objects.update(available_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(deliver_batch()['sent'],1);self.assertEqual(deliver_batch()['sent'],0)
        self.assertEqual(len(mail.outbox),1);self.assertEqual(len(mail.outbox[0].alternatives),1)
        self.assertNotIn('Motivation synthétique',mail.outbox[0].body)
    @override_settings(CONTACT_RECIPIENT='')
    def test_contact_no_invented_receipt(self):
        submit(ContactForm(submission('contact')));self.assertEqual(OutboxMessage.objects.count(),0)
    def test_state_change_permissions_and_audit(self):
        obj=submit(ApplicationForm(submission()))
        allowed_roles={Role.PRESIDENT,Role.GMT}
        for role in Role.values:
            actor=account(role+'@example.invalid',role=role)
            self.assertEqual(can(actor,'application.view'),role in allowed_roles)
            self.assertEqual(can(actor,'application.manage'),role in allowed_roles)
            audits_before=AuditEvent.objects.filter(action='application.state_changed').count()
            state_before=obj.state
            if role in allowed_roles:
                self.assertEqual(change_state(actor=actor,obj=obj,state='CONTACTED').state,'CONTACTED')
            else:
                with self.assertRaises(PermissionDenied):change_state(actor=actor,obj=obj,state='CLOSED')
            obj.refresh_from_db()
            self.assertEqual(obj.state,'CONTACTED' if role in allowed_roles else state_before)
            expected_delta=1 if role in allowed_roles else 0
            self.assertEqual(AuditEvent.objects.filter(action='application.state_changed').count(),audits_before+expected_delta)
        self.assertEqual(AuditEvent.objects.filter(action='application.state_changed').count(),2)

    def test_application_state_http_permissions_and_invalid_state(self):
        obj=submit(ApplicationForm(submission()))
        url=reverse('communications:request',kwargs={'kind':'application','object_id':obj.pk})
        allowed_roles={Role.PRESIDENT,Role.GMT}
        self.assertEqual(self.client.get(url).status_code,302)
        for role in Role.values:
            actor=account('http-'+role+'@example.invalid',role=role)
            self.client.force_login(actor)
            expected=200 if role in allowed_roles else 403
            self.assertEqual(self.client.get(url).status_code,expected)
            audits_before=AuditEvent.objects.filter(action='application.state_changed').count()
            state_before=obj.state
            response=self.client.post(url,{'state':'FOLLOW_UP'})
            self.assertEqual(response.status_code,302 if role in allowed_roles else 403)
            obj.refresh_from_db()
            self.assertEqual(obj.state,'FOLLOW_UP' if role in allowed_roles else state_before)
            self.assertEqual(AuditEvent.objects.filter(action='application.state_changed').count(),audits_before+(1 if role in allowed_roles else 0))
            self.client.logout()
        actor=account('invalid-state@example.invalid',role=Role.PRESIDENT)
        audits_before=AuditEvent.objects.filter(action='application.state_changed').count()
        with self.assertRaises(ValidationError):change_state(actor=actor,obj=obj,state='INVALID')
        obj.refresh_from_db()
        self.assertEqual(obj.state,'FOLLOW_UP')
        self.assertEqual(AuditEvent.objects.filter(action='application.state_changed').count(),audits_before)

from concurrent.futures import ThreadPoolExecutor
from django.db import connections
from django.test import TransactionTestCase

class ConcurrentSubmissionTests(TransactionTestCase):
    def test_same_token_concurrent_posts_persist_once(self):
        data=submission()
        def worker(_):
            try:return submit(ApplicationForm(data)).pk
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:ids=list(pool.map(worker,range(2)))
        self.assertEqual(ids[0],ids[1]);self.assertEqual(MembershipApplication.objects.count(),1);self.assertEqual(OutboxMessage.objects.count(),1)
    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_workers_claim_once(self):
        submit(ApplicationForm(submission()))
        def worker(_):
            try:return deliver_batch()
            finally:connections.close_all()
        with patch('apps.communications.outbox.EmailMultiAlternatives.send',return_value=1) as send:
            with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,range(2)))
        self.assertEqual(send.call_count,1);self.assertEqual(sum(r['sent'] for r in results),1)
    @override_settings(EMAIL_BACKEND='django.core.mail.backends.dummy.EmailBackend')
    def test_dummy_backend_does_not_mark_delivered(self):
        submit(ApplicationForm(submission()));self.assertTrue(deliver_batch()['disabled']);self.assertEqual(OutboxMessage.objects.get().state,'PENDING')
    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_expired_lease_recovered_and_attempt_limit(self):
        submit(ApplicationForm(submission()))
        OutboxMessage.objects.update(state='SENDING',attempts=1,lease_until=timezone.now()-timedelta(minutes=1))
        self.assertEqual(deliver_batch()['sent'],1)
        OutboxMessage.objects.update(state='PENDING',attempts=5,available_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(deliver_batch()['sent'],0);self.assertEqual(OutboxMessage.objects.get().state,'FAILED')

class EditorialBoundaryTests(TestCase):
    def setUp(self):self.actor=account(role=Role.PRESIDENT)
    def test_only_validated_editorial_and_bureau(self):
        from apps.governance.models import LionsYear, Mandate
        EditorialSection.objects.create(key='club_history',title='Histoire synthétique',body='Texte non validé',source='Source test',updated_by=self.actor)
        self.assertNotContains(self.client.get('/notre-club/'),'Texte non validé')
        EditorialSection.objects.update(validated_at=timezone.now())
        self.assertContains(self.client.get('/notre-club/'),'Texte non validé')
        today=timezone.localdate()
        year=LionsYear.objects.create(starts_on=today-timedelta(days=1),ends_on=today+timedelta(days=365))
        mandate=Mandate.objects.create(profile=self.actor.member_profile,function='Fonction publique synthétique',lions_year=year,starts_on=year.starts_on,ends_on=year.ends_on)
        self.assertNotContains(self.client.get('/notre-club/'),mandate.function)
        mandate.validated_at=timezone.now();mandate.validated_by=self.actor;mandate.public_authorized=True;mandate.save()
        self.assertContains(self.client.get('/notre-club/'),mandate.function)
        self.assertNotContains(self.client.get('/notre-club/'),self.actor.email)
    def test_metrics_require_validation(self):
        metric=ImpactMetric.objects.create(label='Mesure synthétique',value=7,starts_on=timezone.localdate(),ends_on=timezone.localdate(),source='Source test',updated_by=self.actor)
        self.assertNotContains(self.client.get('/'),metric.label)
        metric.validated_at=timezone.now();metric.save();self.assertContains(self.client.get('/'),metric.label)
    def test_invalid_request_state_is_controlled(self):
        obj=submit(ContactForm(submission('contact')));self.client.force_login(self.actor)
        url=reverse('communications:request',kwargs={'kind':'contact','object_id':obj.pk})
        self.assertEqual(self.client.post(url,{'state':'BAD'}).status_code,400)
        self.assertEqual(self.client.post(url,{'state':'FOLLOW_UP'}).status_code,302)
        obj.refresh_from_db();self.assertEqual(obj.state,'FOLLOW_UP')
    def test_forged_gallery_id_and_unapproved_cover(self):
        from apps.core.models import PublicImage
        obj=content(self.actor);self.client.force_login(self.actor)
        url=reverse('editorial_management:gallery',kwargs={'object_id':obj.pk})
        self.assertEqual(self.client.post(url,{'image':'not-a-uuid'}).status_code,404)
        image=PublicImage.objects.create(small_key='synthetic',large_key='synthetic2',width=10,height=10,alt='Image non autorisée',source='Test',uploaded_by=self.actor)
        obj.cover=image;obj.save()
        with self.assertRaises(ValidationError):publish_content(actor=self.actor,obj=obj,kind='action')
