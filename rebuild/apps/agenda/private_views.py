import calendar as calendar_module
from datetime import datetime, timedelta, date
from django.contrib import messages
from django.core.exceptions import ValidationError, PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_safe
from apps.core.permissions import capability_required, can
from apps.members.models import MemberProfile
from .models import Event, Registration
from .selectors import upcoming_events, event_by_id, own_registration, attendance_rows, require, events_in_range, calendar_feed_events
from .services import set_registration, record_attendance, create_calendar_event, ensure_calendar_token, regenerate_calendar_token
from .forms import QuickEventForm
from .ics import build_calendar

TUNIS = timezone.get_default_timezone()


def _parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return timezone.localdate()


def _aware(d, t=None):
    return timezone.make_aware(datetime.combine(d, t or datetime.min.time()))


def _event_row(request, event):
    confirmed = event.registrations.filter(status=Registration.Status.CONFIRMED).count()
    return {
        "event": event,
        "registration": own_registration(request.user, event),
        "confirmed": confirmed,
        "remaining": None if event.capacity is None else max(event.capacity - confirmed, 0),
    }


@capability_required("event.register")
@require_safe
def calendar(request):
    view = request.GET.get("view") if request.GET.get("view") in {"month", "week", "day"} else "month"
    ref = _parse_date(request.GET.get("date"))
    can_create = can(request.user, "event.create")
    context = {"view": view, "ref_date": ref, "today": timezone.localdate(), "can_create": can_create,
        "quick_form": QuickEventForm(initial={"starts_at": timezone.localtime().replace(minute=0, second=0, microsecond=0)})}

    if view == "day":
        start = _aware(ref)
        end = _aware(ref + timedelta(days=1))
        events = list(events_in_range(request.user, start, end))
        context.update(prev_date=ref - timedelta(days=1), next_date=ref + timedelta(days=1),
            day_rows=[_event_row(request, e) for e in events], label=ref.strftime("%A %d %B %Y"), all_events=events)
    elif view == "week":
        monday = ref - timedelta(days=ref.weekday())
        start = _aware(monday)
        end = _aware(monday + timedelta(days=7))
        events = list(events_in_range(request.user, start, end))
        days = []
        for i in range(7):
            day = monday + timedelta(days=i)
            day_events = [e for e in events if timezone.localtime(e.starts_at).date() <= day <= timezone.localtime(e.ends_at).date()]
            days.append({"date": day, "events": day_events, "is_today": day == context["today"]})
        context.update(prev_date=monday - timedelta(days=7), next_date=monday + timedelta(days=7),
            week_days=days, label=f"{monday.strftime('%d %b')} – {(monday+timedelta(days=6)).strftime('%d %b %Y')}", all_events=events)
    else:
        first_of_month = ref.replace(day=1)
        cal = calendar_module.Calendar(firstweekday=0)
        month_dates = list(cal.itermonthdates(ref.year, ref.month))
        start = _aware(month_dates[0])
        end = _aware(month_dates[-1] + timedelta(days=1))
        events = list(events_in_range(request.user, start, end))
        by_day = {}
        for e in events:
            d0, d1 = timezone.localtime(e.starts_at).date(), timezone.localtime(e.ends_at).date()
            d = d0
            while d <= d1:
                by_day.setdefault(d, []).append(e)
                d += timedelta(days=1)
        weeks = []
        for w in range(0, len(month_dates), 7):
            week = []
            for d in month_dates[w:w+7]:
                week.append({"date": d, "in_month": d.month == ref.month, "is_today": d == context["today"], "events": by_day.get(d, [])})
            weeks.append(week)
        if ref.month == 1:
            prev_month = ref.replace(year=ref.year - 1, month=12, day=1)
        else:
            prev_month = ref.replace(month=ref.month - 1, day=1)
        if ref.month == 12:
            next_month = ref.replace(year=ref.year + 1, month=1, day=1)
        else:
            next_month = ref.replace(month=ref.month + 1, day=1)
        context.update(prev_date=prev_month, next_date=next_month, weeks=weeks, label=first_of_month.strftime("%B %Y"), all_events=events)

    context["detail_rows"] = [_event_row(request, e) for e in context.get("all_events", [])]
    profile = request.user.member_profile
    token = ensure_calendar_token(profile)
    context["subscribe_url"] = request.build_absolute_uri(reverse("agenda_private:calendar_subscribe", args=[token]))
    return render(request, "espace/calendrier.html", context)


@capability_required("event.create")
@require_http_methods(["POST"])
def calendar_event_add(request):
    form = QuickEventForm(request.POST)
    if form.is_valid():
        try:
            create_calendar_event(actor=request.user, title=form.cleaned_data["title"],
                description=form.cleaned_data["description"], starts_at=form.cleaned_data["starts_at"],
                ends_at=form.cleaned_data["ends_at"], all_day=form.cleaned_data["all_day"],
                location=form.cleaned_data["location"], meeting_link=form.cleaned_data["meeting_link"])
            messages.success(request, "Événement ajouté au calendrier interne.")
        except ValidationError as error:
            messages.error(request, " ".join(error.messages) if hasattr(error, "messages") else str(error))
    else:
        messages.error(request, "Formulaire invalide : " + " ".join(f"{k} : {', '.join(v)}" for k, v in form.errors.items()))
    return redirect(request.POST.get("next") or "agenda_private:calendar")


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
    return redirect(request.POST.get("next") or "agenda_private:calendar")


@capability_required("event.register")
@require_safe
def calendar_download(request):
    events = calendar_feed_events(request.user)
    if events is None:
        raise Http404
    response = HttpResponse(build_calendar(events), content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="lionsmed-calendrier.ics"'
    response["Cache-Control"] = "private, no-store"
    response["X-Robots-Tag"] = "noindex"
    return response


@capability_required("event.register")
@require_http_methods(["POST"])
def calendar_token_regenerate(request):
    regenerate_calendar_token(actor=request.user, profile=request.user.member_profile)
    messages.success(request, "Lien de synchronisation régénéré. L’ancien lien ne fonctionne plus.")
    return redirect("agenda_private:calendar")


@require_safe
def calendar_subscribe(request, token):
    # Point d'accès anonyme volontaire : les applications calendrier ne s'authentifient
    # pas. La sécurité tient au jeton aléatoire, jamais à une session.
    profile = MemberProfile.objects.filter(calendar_token=token).select_related("user").first()
    if not profile:
        raise Http404
    events = calendar_feed_events(profile.user)
    if events is None:
        raise Http404
    response = HttpResponse(build_calendar(events), content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = 'inline; filename="lionsmed-calendrier.ics"'
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


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
