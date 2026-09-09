from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
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
