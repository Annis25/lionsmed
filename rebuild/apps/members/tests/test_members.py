from datetime import date, timedelta
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch
from PIL import Image
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from django.db import transaction, IntegrityError
from apps.core.tests.test_foundations import account
from apps.core.permissions import can, CAPABILITIES, MANAGERS, effective_role
from apps.core.models import AuditEvent
from apps.members.models import MemberProfile, AssociationExperience
from apps.members.forms import ProfileForm
from apps.members.services import update_profile, save_experience, delete_experience
from apps.members.selectors import profile_data, scoped_profiles
from apps.members.uploads import encode_photo, photo_storage, MAX_BYTES
from apps.governance.models import Role, LionsYear, Mandate
from apps.governance.mandates import save_mandate
from apps.accounts.email_changes import validate_new_email, request_email_change

PROFILE={"first_name":"Prénom synthétique","last_name":"Nom synthétique","phone":"00000","profession":"Profession privée","bio":"Bio privée"}
EXPERIENCE={"network":"LEO","club":"Club synthétique","function":"Président historique","district":"District synthétique","start_year":"2020","end_year":"2021","description":"Description privée","achievements":"Réalisations privées"}

def picture(name="portrait.png", kind="PNG", mime="image/png", size=(80,80)):
    out=BytesIO();Image.new("RGB",size,"blue").save(out,format=kind)
    return SimpleUploadedFile(name,out.getvalue(),content_type=mime)

class MemberTests(TestCase):
    def setUp(self):
        self.actor=account();self.other=account("other@example.invalid")
        self.client.force_login(self.actor)
        self.p=self.actor.member_profile

    def test_defaults_private_and_no_identity_duplication(self):
        for field in ["directory_visible","share_profession","share_contacts","share_bio","share_photo","share_experiences","share_mandates"]:
            self.assertFalse(getattr(self.p,field))
        self.assertFalse({"email","first_name","last_name","role"}&{f.name for f in MemberProfile._meta.fields})

    def test_own_profile_and_update(self):
        self.assertEqual(self.client.get(reverse("members:profile")).status_code,200)
        result=self.client.post(reverse("members:profile_edit"),PROFILE)
        self.assertEqual(result.status_code,302)
        self.p.refresh_from_db();self.actor.refresh_from_db()
        self.assertEqual(self.p.phone,"00000");self.assertEqual(self.actor.first_name,PROFILE["first_name"])

    def test_forged_fields_never_mutate_account_or_status(self):
        original=self.actor.email
        data={**PROFILE,"email":"stolen@example.invalid","role":"SUPER_ADMIN","is_staff":"1","is_superuser":"1","is_active":"0","status":"SUSPENDED","user":str(self.other.pk),"photo_key":"secret"}
        self.client.post(reverse("members:profile_edit"),data)
        self.actor.refresh_from_db();self.p.refresh_from_db()
        self.assertEqual(self.actor.email,original);self.assertFalse(self.actor.is_staff);self.assertFalse(self.actor.is_superuser)
        self.assertTrue(self.actor.is_active);self.assertEqual(self.p.status,"ACTIVE");self.assertEqual(self.p.photo_key,"")
        self.assertEqual(effective_role(self.actor),Role.MEMBRE)

    def test_email_not_a_profile_form_field(self):
        form=ProfileForm(actor=self.actor,profile=self.p)
        self.assertNotIn("email",form.fields)
        self.assertNotContains(self.client.get(reverse("members:profile_edit")), 'name="email"')

    def test_profile_service_idor(self):
        with self.assertRaises(PermissionDenied): update_profile(actor=self.actor,profile=self.other.member_profile,data=PROFILE)
        with self.assertRaises(PermissionDenied): ProfileForm(actor=self.actor,profile=self.other.member_profile)

    def test_bad_profile_has_accessible_errors(self):
        response=self.client.post(reverse("members:profile_edit"),{"first_name":""})
        self.assertEqual(response.status_code,200);self.assertContains(response,'aria-invalid="true"');self.assertContains(response,'errorlist')

    def test_suspended_denied(self):
        MemberProfile.objects.filter(pk=self.p.pk).update(status="SUSPENDED")
        self.assertEqual(self.client.get(reverse("members:profile")).status_code,403)
        self.assertEqual(self.client.post(reverse("members:profile_edit"),PROFILE).status_code,403)

    def test_inactive_denied(self):
        get_user_model().objects.filter(pk=self.actor.pk).update(is_active=False)
        self.assertEqual(self.client.get(reverse("members:profile")).status_code,302)

    def test_csrf_profile_and_experience(self):
        client=Client(enforce_csrf_checks=True);client.force_login(self.actor)
        for route in ["members:profile_edit","members:experience_add"]:
            self.assertEqual(client.post(reverse(route),PROFILE).status_code,403)

    def test_no_mutation_through_other_profile_url(self):
        self.assertIn(self.client.post(reverse("members:detail",args=[self.other.pk]),PROFILE).status_code,[404,405])
        self.other.refresh_from_db();self.assertNotEqual(self.other.first_name,PROFILE["first_name"])

class DirectoryTests(TestCase):
    def setUp(self):
        self.actor=account();self.other=account("hidden@example.invalid")
        self.client.force_login(self.actor)
        self.p=self.other.member_profile
        self.p.phone="secret-phone";self.p.profession="secret-profession";self.p.bio="secret-bio";self.p.save()

    def publish(self,**flags):
        self.p.directory_visible=True
        for k,v in flags.items():setattr(self.p,k,v)
        self.p.save()

    def test_hidden_profile_is_not_listed_or_readable(self):
        self.assertNotContains(self.client.get(reverse("members:directory")),str(self.other.pk))
        self.assertEqual(self.client.get(reverse("members:detail",args=[self.other.pk])).status_code,404)

    def test_private_fields_absent_from_html_and_context(self):
        self.publish()
        response=self.client.get(reverse("members:detail",args=[self.other.pk]))
        for value in [self.other.email,self.p.phone,self.p.bio,self.p.profession]:self.assertNotContains(response,value)
        for key in ["email","phone","bio","profession","photo_key","user"]:self.assertNotIn(key,response.context["member"])

    def test_opt_in_exposes_only_selected_fields(self):
        self.publish(share_profession=True)
        response=self.client.get(reverse("members:detail",args=[self.other.pk]))
        self.assertContains(response,self.p.profession);self.assertNotContains(response,self.other.email)
        self.publish(share_contacts=True)
        self.assertContains(self.client.get(reverse("members:detail",args=[self.other.pk])),self.other.email)

    def test_search_does_not_probe_hidden_profession(self):
        self.publish()
        response=self.client.get(reverse("members:directory"),{"q":"secret-profession"})
        self.assertEqual(response.context["page_obj"].paginator.count,0)
        self.publish(share_profession=True)
        self.assertEqual(self.client.get(reverse("members:directory"),{"q":"secret-profession"}).context["page_obj"].paginator.count,1)

    def test_role_filter_and_name_search(self):
        self.publish()
        self.assertEqual(self.client.get(reverse("members:directory"),{"role":"MEMBRE","q":"Synthétique"}).context["page_obj"].paginator.count,1)
        self.assertEqual(self.client.get(reverse("members:directory"),{"role":"PRESIDENT"}).context["page_obj"].paginator.count,0)

    def test_inactive_suspended_expired_revoked_excluded(self):
        self.publish()
        for field,value in [("status","SUSPENDED")]:
            setattr(self.p,field,value);self.p.save()
            self.assertEqual(scoped_profiles(self.actor).count(),0)
        self.p.status="ACTIVE";self.p.save()
        self.other.role_grants.update(ends_at=timezone.now()-timedelta(minutes=1))
        self.assertEqual(scoped_profiles(self.actor).count(),0)

    def test_guest_denied_even_if_opted_in(self):
        guest=account("guest@example.invalid",role=Role.INVITE)
        self.client.force_login(guest)
        self.assertEqual(self.client.get(reverse("members:directory")).status_code,403)
        self.assertEqual(self.client.get(reverse("members:detail",args=[self.other.pk])).status_code,403)

    def test_management_has_no_private_contact_bypass(self):
        manager=account("manager@example.invalid",role=Role.PRESIDENT)
        dto=profile_data(manager,self.p,management=True)
        self.assertNotIn("email",dto);self.assertNotIn("phone",dto)
        self.assertIn("status",dto)

    def test_pagination(self):
        for i in range(14):
            u=account(f"page{i}@example.invalid");MemberProfile.objects.filter(user=u).update(directory_visible=True)
        page=self.client.get(reverse("members:directory"),{"page":2}).context["page_obj"]
        self.assertEqual(len(page),2)

class ExperienceTests(TestCase):
    def setUp(self):
        self.actor=account();self.other=account("other@example.invalid");self.client.force_login(self.actor)

    def create(self,user=None):
        p=(user or self.actor).member_profile
        result=save_experience(actor=user or self.actor,profile=p,data=EXPERIENCE)
        self.assertIsNone(result)
        return p.experiences.get()

    def test_crud_own_and_no_role_effect(self):
        self.assertEqual(self.client.post(reverse("members:experience_add"),EXPERIENCE).status_code,302)
        exp=self.actor.member_profile.experiences.get()
        self.assertEqual(effective_role(self.actor),Role.MEMBRE)
        response=self.client.post(reverse("members:experience_edit",args=[exp.pk]),{**EXPERIENCE,"function":"Autre fonction"})
        self.assertEqual(response.status_code,302);exp.refresh_from_db();self.assertEqual(exp.function,"Autre fonction")
        self.assertEqual(self.client.get(reverse("members:experience_delete",args=[exp.pk])).status_code,200)
        self.assertTrue(AssociationExperience.objects.filter(pk=exp.pk).exists())
        self.client.post(reverse("members:experience_delete",args=[exp.pk]))
        self.assertFalse(AssociationExperience.objects.filter(pk=exp.pk).exists())

    def test_idor_read_edit_delete(self):
        exp=self.create(self.other)
        for route in ["members:experience_edit","members:experience_delete"]:
            self.assertEqual(self.client.get(reverse(route,args=[exp.pk])).status_code,404)
            self.assertEqual(self.client.post(reverse(route,args=[exp.pk]),EXPERIENCE).status_code,404)
        with self.assertRaises(PermissionDenied):delete_experience(actor=self.actor,experience=exp)

    def test_service_cannot_reassign_experience(self):
        exp=self.create()
        with self.assertRaises(PermissionDenied):save_experience(actor=self.actor,profile=self.other.member_profile,data=EXPERIENCE,experience=exp)

    def test_forged_owner_ignored(self):
        self.client.post(reverse("members:experience_add"),{**EXPERIENCE,"profile":self.other.member_profile.pk})
        self.assertEqual(self.actor.member_profile.experiences.count(),1)
        self.assertEqual(self.other.member_profile.experiences.count(),0)

    def test_years_ordered_and_end_optional(self):
        response=self.client.post(reverse("members:experience_add"),{**EXPERIENCE,"end_year":"2019"})
        self.assertEqual(response.status_code,200);self.assertEqual(AssociationExperience.objects.count(),0)
        response=self.client.post(reverse("members:experience_add"),{**EXPERIENCE,"end_year":""})
        self.assertEqual(response.status_code,302)
        exp=AssociationExperience.objects.get()
        self.assertIsNone(exp.end_year)

class UploadTests(TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.override=override_settings(PRIVATE_MEDIA_ROOT=self.tmp.name);self.override.enable();self.addCleanup(self.override.disable)
        self.actor=account();self.other=account("other@example.invalid");self.client.force_login(self.actor)

    def upload(self,photo):
        return self.client.post(reverse("members:profile_edit"),{**PROFILE,"photo":photo})

    def test_valid_reencoded_random_private_photo(self):
        self.assertEqual(self.upload(picture()).status_code,302)
        self.actor.member_profile.refresh_from_db();key=self.actor.member_profile.photo_key
        self.assertRegex(key,r"^portraits/[a-f0-9]{32}\.jpg$")
        with photo_storage().open(key) as file:
            with Image.open(file) as im:self.assertEqual(im.format,"JPEG");self.assertFalse(im.getexif())
        response=self.client.get(reverse("members:photo",args=[self.actor.pk]))
        self.assertEqual(response.status_code,200);self.assertEqual(response["Cache-Control"],"private, no-store");b"".join(response.streaming_content)

    def test_svg_invalid_and_mime_extension_mismatch(self):
        files=[SimpleUploadedFile("bad.svg",b"<svg></svg>",content_type="image/svg+xml"),SimpleUploadedFile("bad.png",b"bad",content_type="image/png"),picture(name="lie.jpg"),picture(mime="image/jpeg")]
        for file in files:
            with self.subTest(name=file.name):self.assertEqual(self.upload(file).status_code,200)
        self.actor.member_profile.refresh_from_db();self.assertEqual(self.actor.member_profile.photo_key,"")

    def test_too_large_and_too_many_pixels(self):
        with self.assertRaises(ValidationError):encode_photo(SimpleUploadedFile("big.png",b"x"*(MAX_BYTES+1),content_type="image/png"))
        with self.assertRaises(ValidationError):encode_photo(picture(size=(4100,4100)))

    def test_other_photo_denied_then_opt_in_and_revocation(self):
        self.upload(picture());self.client.force_login(self.other)
        url=reverse("members:photo",args=[self.actor.pk])
        self.assertEqual(self.client.get(url).status_code,404)
        MemberProfile.objects.filter(user=self.actor).update(directory_visible=True,share_photo=True)
        response=self.client.get(url);self.assertEqual(response.status_code,200);b"".join(response.streaming_content)
        MemberProfile.objects.filter(user=self.actor).update(share_photo=False)
        self.assertEqual(self.client.head(url).status_code,404)
        self.assertEqual(self.client.get("/media/portraits/anything.jpg").status_code,404)

    def test_replacement_and_deletion_remove_old_file_after_commit(self):
        self.upload(picture());self.actor.member_profile.refresh_from_db();old=self.actor.member_profile.photo_key
        with self.captureOnCommitCallbacks(execute=True):self.upload(picture())
        self.assertFalse(photo_storage().exists(old))
        self.actor.member_profile.refresh_from_db();new=self.actor.member_profile.photo_key
        with self.captureOnCommitCallbacks(execute=True):self.client.post(reverse("members:profile_edit"),{**PROFILE,"remove_photo":"on"})
        self.assertFalse(photo_storage().exists(new))

    def test_rollback_removes_new_file(self):
        with patch.object(MemberProfile,"save",side_effect=IntegrityError):
            with self.assertRaises(IntegrityError):self.upload(picture())
        self.assertEqual(photo_storage().listdir("portraits")[1],[])

    def test_upload_http_limit_no_profile_mutation(self):
        response=self.upload(SimpleUploadedFile("big.png",b"x"*(MAX_BYTES+1),content_type="image/png"))
        self.assertEqual(response.status_code,400)
        self.actor.refresh_from_db();self.assertEqual(self.actor.first_name,"Compte")

    def test_exif_orientation_and_metadata_removed(self):
        out=BytesIO();im=Image.new("RGB",(80,40),"red")
        exif=Image.Exif();exif[274]=6;exif[270]="Sensitive metadata"
        im.save(out,format="JPEG",exif=exif)
        encoded=encode_photo(SimpleUploadedFile("rotated.jpg",out.getvalue(),content_type="image/jpeg"))
        with Image.open(encoded) as result:
            self.assertEqual(result.size,(40,80));self.assertFalse(result.getexif())
        self.assertNotIn(b"Sensitive metadata",encoded.read())

    def test_private_photo_anonymous_and_guest_refused(self):
        self.upload(picture());MemberProfile.objects.filter(user=self.actor).update(directory_visible=True,share_photo=True)
        url=reverse("members:photo",args=[self.actor.pk])
        self.client.logout();self.assertEqual(self.client.get(url).status_code,302)
        self.client.force_login(account("guest@example.invalid",role=Role.INVITE))
        self.assertEqual(self.client.get(url).status_code,403)


class GovernanceTests(TestCase):
    def setUp(self):
        self.actor=account();self.year=LionsYear.objects.create(starts_on=date(2020,1,1),ends_on=date(2021,1,1))
        self.data={"profile":self.actor.member_profile,"function":"Président","lions_year":self.year,"starts_on":date(2020,2,1),"ends_on":date(2020,12,1)}

    def test_all_roles_cannot_mutate_mandates_or_email(self):
        for role in Role.values:
            u=account(role.lower()+"@example.invalid",role=role)
            with self.assertRaises(PermissionDenied):save_mandate(actor=u,data=self.data)
            with self.assertRaises(PermissionDenied):request_email_change(actor=u,user=u,new_email="new@example.invalid")
        self.assertEqual(Mandate.objects.count(),0)

    def test_mandate_has_no_permission_effect(self):
        mandate=Mandate.objects.create(**self.data)
        mandate.function="Super administrateur";mandate.save()
        self.assertEqual(effective_role(self.actor),Role.MEMBRE)
        self.actor.role_grants.all().delete()
        self.assertIsNone(effective_role(self.actor))

    def test_year_bounds_validation(self):
        m=Mandate(**{**self.data,"ends_on":date(2022,1,1)})
        with self.assertRaises(ValidationError):m.full_clean()

    def test_future_mandate_service_validates_and_audits_without_grant(self):
        # Délégation simulée dans ce test seulement, jamais configuration de production.
        with patch.dict(CAPABILITIES,{"mandate.manage":frozenset({Role.MEMBRE})}):
            m=save_mandate(actor=self.actor,data=self.data)
            self.assertEqual(AuditEvent.objects.filter(action="mandate.saved").count(),1)
            m.function="Autre";save_mandate(actor=self.actor,data={"function":"Autre"},mandate=m)
            with self.assertRaises(ValidationError):save_mandate(actor=self.actor,data={**self.data,"ends_on":date(2022,1,1)})
        self.assertEqual(effective_role(self.actor),Role.MEMBRE)

    def test_email_normalization_uniqueness_and_no_fake_confirmation(self):
        self.assertEqual(validate_new_email(" New@Example.INVALID "),"new@example.invalid")
        with self.assertRaises(ValidationError):validate_new_email(self.actor.email.upper())
        with patch.dict(CAPABILITIES,{"account.change_email":frozenset({Role.MEMBRE})}):
            with self.assertRaises(ValidationError):request_email_change(actor=self.actor,user=self.actor,new_email="new@example.invalid")
        self.actor.refresh_from_db();self.assertEqual(self.actor.email,"member@example.invalid")

    def test_full_view_matrix_seven_roles(self):
        own=["members:profile","members:profile_edit","members:experiences","members:experience_add","members:email_information"]
        management=["governance:dashboard","governance:members","governance:years"]
        for role in Role.values:
            u=account(role.lower()+"@example.invalid",role=role);self.client.force_login(u)
            for route in own+management+["members:directory"]:
                expected=200 if route in own or (route in management and role in MANAGERS) or (route=="members:directory" and role!=Role.INVITE) else 403
                response=self.client.get(reverse(route))
                self.assertEqual(response.status_code,expected,(role,route))
                self.assertIn("noindex",response["X-Robots-Tag"])
            self.assertEqual(self.client.post(reverse("governance:members"),{"role":"SUPER_ADMIN"}).status_code,405 if role in MANAGERS else 403)
        self.client.logout()
        for route in own+management+["members:directory"]:self.assertEqual(self.client.get(reverse(route)).status_code,302)

    def test_management_detail_matrix_and_private_detail(self):
        MemberProfile.objects.filter(user=self.actor).update(directory_visible=True)
        for role in Role.values:
            u=account(role.lower()+"@example.invalid",role=role);self.client.force_login(u)
            self.assertEqual(self.client.get(reverse("governance:member",args=[self.actor.pk])).status_code,200 if role in MANAGERS else 403)
            self.assertEqual(self.client.get(reverse("members:detail",args=[self.actor.pk])).status_code,403 if role==Role.INVITE else 200)
