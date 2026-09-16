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
def create_calendar_event(*, actor, title, description, starts_at, ends_at, all_day, location, meeting_link, creation_key=None):
    """Ajout rapide depuis le calendrier interne : jamais public par défaut (`visibility`
    reste PRIVATE — la publication publique passe par le workflow éditorial existant,
    /espace/contenu/, jamais automatique)."""
    require(actor, "event.create")
    from django.contrib.auth import get_user_model
    actor = get_user_model().objects.select_for_update().get(pk=actor.pk)
    if creation_key:
        existing = Event.objects.filter(creation_key=creation_key).first()
        if existing:
            if existing.created_by_id != actor.pk:
                raise PermissionDenied
            return existing
    if not title or not title.strip():
        raise ValidationError("Le titre est obligatoire.")
    if not starts_at:
        raise ValidationError("La date et l'heure de début sont obligatoires.")
    if ends_at and ends_at <= starts_at:
        raise ValidationError("La fin doit être postérieure au début.")
    base = slugify(title)[:150] or "evenement"
    slug = f"{base}-{secrets.token_hex(4)}"
    from datetime import timedelta
    event = Event(title=title[:180], slug=slug, summary=(description or "")[:500], body=description or "", creation_key=creation_key,
        starts_at=starts_at, ends_at=ends_at or starts_at + timedelta(hours=1), all_day=all_day, location=location[:200],
        meeting_link=meeting_link or "", visibility="PRIVATE",
        status="PUBLISHED", published_at=timezone.now(), created_by=actor, updated_by=actor)
    event.meta_title = event.title
    event.meta_description = event.summary[:300]
    event.full_clean()
    event.save()
    audit(actor, "event.created_from_calendar", event)
    notify_event_created(event)
    return event


@transaction.atomic
def update_calendar_event(*, actor, event, title, description, starts_at, ends_at,
        all_day, location, meeting_link, category, registration_enabled, capacity):
    """Modifie les informations de calendrier sans altérer la fiche éditoriale.

    L'opération est sérialisée et auditée. Elle ne déclenche pas une seconde annonce
    e-mail : la règle produit ne notifie que la création d'un événement proche.
    """
    require(actor, "event.edit", event)
    event = Event.objects.select_for_update().get(pk=event.pk)
    if event.status != "PUBLISHED":
        raise ValidationError("Cet événement n'est plus actif.")
    if not title or not title.strip():
        raise ValidationError("Le titre est obligatoire.")
    if not starts_at:
        raise ValidationError("La date et l'heure de début sont obligatoires.")
    if ends_at and ends_at <= starts_at:
        raise ValidationError("La fin doit être postérieure au début.")
    if capacity is not None and capacity < 1:
        raise ValidationError("La capacité doit être supérieure à zéro.")

    from datetime import timedelta
    event.title = title.strip()[:180]
    event.summary = (description or "")[:500]
    event.body = description or ""
    event.starts_at = starts_at
    event.ends_at = ends_at or starts_at + timedelta(hours=1)
    event.all_day = bool(all_day)
    event.location = (location or "")[:200]
    event.meeting_link = meeting_link or ""
    event.category = category
    event.registration_enabled = bool(registration_enabled)
    event.capacity = capacity if registration_enabled else None
    event.meta_title = event.title
    event.meta_description = event.summary[:300]
    event.updated_by = actor
    event.full_clean()
    event.save()
    audit(actor, "event.updated_from_calendar", event)
    return event


@transaction.atomic
def cancel_calendar_event(*, actor, event):
    """Retire l'événement du calendrier en préservant son historique relationnel."""
    require(actor, "event.edit", event)
    event = Event.objects.select_for_update().get(pk=event.pk)
    if event.status != "PUBLISHED":
        raise ValidationError("Cet événement est déjà annulé ou retiré.")
    event.status = "ARCHIVED"
    event.updated_by = actor
    event.full_clean()
    event.save(update_fields=["status", "updated_by", "updated_at"])
    audit(actor, "event.cancelled_from_calendar", event)
    return event


@transaction.atomic
def notify_event_created(event):
    """Une annonce par événement/destinataire ; jamais d'annonce à chaque modification."""
    from datetime import timedelta
    from apps.communications.services import broadcast_recipients, notify
    event = Event.objects.select_for_update().get(pk=event.pk)
    now = timezone.now()
    if event.status != "PUBLISHED" or not event.starts_at or not now < event.starts_at <= now + timedelta(days=7):
        return
    for recipient in broadcast_recipients():
        if can(recipient, "event.register", event):
            notify(recipient=recipient, category="EVENT", title=f"Nouvel événement — {event.title}",
                excerpt=f"Le {timezone.localtime(event.starts_at):%d/%m/%Y à %H:%M}.",
                event_key=f"event-created:{event.pk}:{recipient.pk}:v1", target_kind="event", target_id=event.pk,
                email=True, outbox_kind="EVENT_CREATED")


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
