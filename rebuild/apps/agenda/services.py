import secrets
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from apps.core.permissions import can
from apps.core.models import AuditEvent
from apps.editorial.publication import publish_content
from .models import Event, Registration, Attendance

def publish_event(*,actor,event):
    return publish_content(actor=actor,obj=event,kind="event")

def require(actor,capability,obj=None):
    if not can(actor,capability,obj):raise PermissionDenied

def audit(actor,action,obj):
    AuditEvent.objects.create(actor=actor,action=action,object_type=obj._meta.object_name,object_id=str(obj.pk))

@transaction.atomic
def set_registration(*,actor,event,status):
    require(actor,"event.register",event)
    if status not in Registration.Status.values:raise ValidationError("Statut d'inscription invalide.")
    # Verrouille l'événement : sérialise les confirmations concurrentes sur sa capacité.
    event=Event.objects.select_for_update().get(pk=event.pk)
    profile=actor.member_profile
    registration,_=Registration.objects.get_or_create(event=event,profile=profile,defaults={"status":Registration.Status.PENDING})
    if status==Registration.Status.CONFIRMED and registration.status!=Registration.Status.CONFIRMED:
        if not event.registration_enabled:raise ValidationError("Les inscriptions ne sont pas ouvertes pour ce rendez-vous.")
        if event.capacity is not None:
            confirmed=Registration.objects.filter(event=event,status=Registration.Status.CONFIRMED).exclude(pk=registration.pk).count()
            if confirmed>=event.capacity:raise ValidationError("La capacité de ce rendez-vous est atteinte.")
    registration.status=status
    registration.full_clean();registration.save()
    audit(actor,"event.registration_set",registration)
    return registration

@transaction.atomic
def record_attendance(*,actor,event,profile,status,note=""):
    require(actor,"attendance.record")
    if status not in Attendance.Status.values:raise ValidationError("Statut de présence invalide.")
    event=Event.objects.select_for_update().get(pk=event.pk)
    attendance,_=Attendance.objects.get_or_create(event=event,profile=profile,defaults={"status":status,"recorded_by":actor})
    attendance.status=status;attendance.note=note[:300];attendance.recorded_by=actor
    attendance.full_clean();attendance.save()
    audit(actor,"attendance.recorded",attendance)
    return attendance

@transaction.atomic
def create_calendar_event(*, actor, title, description, starts_at, ends_at, all_day, location, meeting_link):
    """Ajout rapide depuis le calendrier interne : jamais public par défaut (`visibility`
    reste PRIVATE — la publication publique passe par le workflow éditorial existant,
    /espace/contenu/, jamais automatique)."""
    require(actor, "event.create")
    if not title or not title.strip():
        raise ValidationError("Le titre est obligatoire.")
    if not starts_at:
        raise ValidationError("La date et l'heure de début sont obligatoires.")
    if ends_at and ends_at <= starts_at:
        raise ValidationError("La fin doit être postérieure au début.")
    base = slugify(title)[:150] or "evenement"
    slug = f"{base}-{secrets.token_hex(4)}"
    event = Event(title=title[:180], slug=slug, summary=(description or "")[:500], body=description or "",
        starts_at=starts_at, ends_at=ends_at or starts_at, all_day=all_day, location=location[:200],
        meeting_link=meeting_link or "", visibility="PRIVATE",
        status="PUBLISHED", published_at=timezone.now(), created_by=actor, updated_by=actor)
    event.meta_title = event.title
    event.meta_description = event.summary[:300]
    event.full_clean()
    event.save()
    audit(actor, "event.created_from_calendar", event)
    return event


@transaction.atomic
def ensure_calendar_token(profile):
    if not profile.calendar_token:
        profile.calendar_token = secrets.token_urlsafe(32)
        profile.save(update_fields=["calendar_token"])
    return profile.calendar_token


@transaction.atomic
def regenerate_calendar_token(*, actor, profile):
    require(actor, "event.register", None)
    if profile.user_id != actor.pk:
        raise PermissionDenied("Vous ne pouvez régénérer que votre propre lien.")
    profile.calendar_token = secrets.token_urlsafe(32)
    profile.save(update_fields=["calendar_token"])
    audit(actor, "calendar.token_regenerated", profile)
    return profile.calendar_token
