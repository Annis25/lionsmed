from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.utils import timezone
from apps.core.permissions import can
from apps.members.models import MemberProfile
from .models import Event, Registration, Attendance

def require(actor,capability,obj=None):
    if not can(actor,capability,obj):raise PermissionDenied

def visible_events(actor):
    require(actor,"event.register")
    return Event.objects.filter(status="PUBLISHED")

def upcoming_events(actor):
    return visible_events(actor).filter(ends_at__gte=timezone.now()).order_by("starts_at")

def events_in_range(actor, start, end):
    """Tout événement chevauchant [start, end) — utilisé par les vues Mois/Semaine/Jour
    et par le flux iCalendar (mêmes règles de visibilité que le calendrier HTML)."""
    return visible_events(actor).filter(starts_at__lt=end, ends_at__gte=start).order_by("starts_at")

def calendar_feed_events(profile_user):
    """Événements exposés dans le flux iCalendar d'un membre, sans levée d'exception si
    ses droits ont changé depuis la génération du lien — l'appelant décide alors du 404."""
    try:
        return list(visible_events(profile_user).order_by("starts_at"))
    except PermissionDenied:
        return None

def event_by_id(actor,event_id):
    try:return visible_events(actor).get(pk=event_id)
    except Event.DoesNotExist:raise Http404

def own_registration(actor,event):
    return Registration.objects.filter(event=event,profile__user_id=actor.pk).first()

def attendance_rows(actor,event):
    require(actor,"attendance.record")
    profiles=MemberProfile.objects.filter(status="ACTIVE",user__is_active=True).select_related("user").order_by("user__last_name","user__first_name")
    registrations={r.profile_id:r for r in event.registrations.all()}
    attendances={a.profile_id:a for a in event.attendances.all()}
    return [{"profile":p,"registration":registrations.get(p.pk),"attendance":attendances.get(p.pk)} for p in profiles]
