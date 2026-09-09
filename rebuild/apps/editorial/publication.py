from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from apps.core.permissions import can
from apps.core.models import AuditEvent
from .models import Redirect

def require(actor, capability, obj=None):
    if not can(actor,capability,obj):raise PermissionDenied

def audit(actor,action,obj):
    AuditEvent.objects.create(actor=actor,action=action,object_type=obj._meta.object_name,object_id=str(obj.pk))

@transaction.atomic
def save_content(*,actor,form,kind,keep_published=False):
    actor=get_user_model().objects.select_for_update().get(pk=actor.pk)
    new=form.instance._state.adding
    require(actor,kind+(".create" if new else ".edit"))
    if not form.is_valid():raise ValidationError("Corrigez les champs indiqués.")
    obj=form.save(commit=False)
    previous=None
    if not new:previous=type(obj).objects.select_for_update().get(pk=obj.pk)
    old_path=previous.get_absolute_url() if previous else None
    if not obj.slug:obj.slug=slugify(obj.title)[:190] or str(obj.pk)
    if type(obj).objects.exclude(pk=obj.pk).filter(slug=obj.slug).exists():raise ValidationError("Ce slug est déjà utilisé.")
    if new or previous.slug!=obj.slug:
        if Redirect.objects.filter(old_path=obj.get_absolute_url()).exists():raise ValidationError("Ce chemin est réservé par une ancienne URL.")
    obj.created_by=previous.created_by if previous else actor
    obj.updated_by=actor
    obj.status="PUBLISHED" if previous and previous.status=="PUBLISHED" and keep_published else "DRAFT"
    obj.published_at=previous.published_at if previous else None
    obj.full_clean();obj.save()
    if previous and previous.slug!=obj.slug:
        Redirect.objects.filter(new_path=old_path).update(new_path=obj.get_absolute_url())
        redirection=Redirect(old_path=old_path,new_path=obj.get_absolute_url());redirection.full_clean();redirection.save()
        audit(actor,"public.slug_changed",obj)
    if previous and previous.status=="PUBLISHED" and not keep_published:audit(actor,"public.withdrawn_for_edit",obj)
    audit(actor,kind+".saved",obj)
    return obj

@transaction.atomic
def publish_content(*,actor,obj,kind):
    actor=get_user_model().objects.select_for_update().get(pk=actor.pk)
    obj=type(obj).objects.select_for_update().get(pk=obj.pk)
    require(actor,kind+".publish",obj)
    if not obj.title or not obj.summary or not obj.body or not obj.slug:raise ValidationError("Titre, slug, résumé et récit sont obligatoires pour publier.")
    for image in [obj.cover,obj.social_image]:
        if image and (not image.approved_at or not image.alt):raise ValidationError("Image non autorisée à publication.")
    if kind=="action":
        if not obj.performed_on or obj.performed_on>timezone.localdate() or not obj.location:raise ValidationError("Une réalisation exige une date passée ou actuelle et un lieu.")
        if obj.photos.filter(image__approved_at__isnull=True).exists():raise ValidationError("La galerie contient une image non autorisée.")
    if kind=="event":
        # Visibilité PRIVATE incluse : un rendez-vous interne doit pouvoir alimenter le calendrier privé.
        if not obj.starts_at or not obj.ends_at or obj.ends_at<=obj.starts_at or not obj.location:raise ValidationError("Dates et lieu requis.")
    obj.meta_title=obj.meta_title or obj.title
    obj.meta_description=obj.meta_description or obj.summary[:300]
    obj.status="PUBLISHED";obj.published_at=obj.published_at or timezone.now();obj.updated_by=actor
    obj.full_clean();obj.save();audit(actor,kind+".published",obj)
    return obj

@transaction.atomic
def withdraw_content(*,actor,obj,kind):
    actor=get_user_model().objects.select_for_update().get(pk=actor.pk)
    obj=type(obj).objects.select_for_update().get(pk=obj.pk)
    require(actor,kind+".publish",obj)
    obj.status="ARCHIVED";obj.updated_by=actor;obj.save(update_fields=["status","updated_by","updated_at"])
    audit(actor,kind+".withdrawn",obj)
