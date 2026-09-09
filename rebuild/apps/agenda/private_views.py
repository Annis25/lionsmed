from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods, require_safe
from apps.core.permissions import capability_required
from apps.members.models import MemberProfile
from .models import Event, Registration
from .selectors import upcoming_events, event_by_id, own_registration, attendance_rows, require
from .services import set_registration, record_attendance


@capability_required("event.register")
@require_safe
def calendar(request):
    events = []
    for event in upcoming_events(request.user):
        confirmed = event.registrations.filter(status=Registration.Status.CONFIRMED).count()
        events.append({
            "event": event,
            "registration": own_registration(request.user, event),
            "confirmed": confirmed,
            "remaining": None if event.capacity is None else max(event.capacity - confirmed, 0),
        })
    return render(request, "espace/calendrier.html", {"events": events})


@capability_required("event.register")
@require_http_methods(["POST"])
def rsvp(request, event_id):
    event = event_by_id(request.user, event_id)
    status = {"confirm": Registration.Status.CONFIRMED, "cancel": Registration.Status.CANCELLED}.get(request.POST.get("action"))
    if status is None:
        raise Http404
    try:
        set_registration(actor=request.user, event=event, status=status)
        messages.success(request, "Votre inscription a été enregistrée.")
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    return redirect("agenda_private:calendar")


@capability_required("attendance.record")
@require_safe
def attendance_events(request):
    events = Event.objects.filter(status="PUBLISHED").order_by("-starts_at")[:50]
    return render(request, "espace/presences.html", {"events": events})


@capability_required("attendance.record")
@require_http_methods(["GET", "POST"])
def attendance_sheet(request, event_id):
    event = get_object_or_404(Event, pk=event_id, status="PUBLISHED")
    require(request.user, "attendance.record")
    if request.method == "POST":
        try:
            profile = MemberProfile.objects.get(pk=request.POST.get("profile_id"), status="ACTIVE")
        except (MemberProfile.DoesNotExist, ValueError, TypeError):
            raise Http404
        status = request.POST.get("status")
        if status not in {"PRESENT", "ABSENT", "EXCUSED"}:
            raise Http404
        try:
            record_attendance(actor=request.user, event=event, profile=profile, status=status, note=request.POST.get("note", ""))
            messages.success(request, "Présence enregistrée.")
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        return redirect("agenda_private:attendance_sheet", event_id=event.pk)
    return render(request, "espace/presence_sheet.html", {"event": event, "rows": attendance_rows(request.user, event)})
