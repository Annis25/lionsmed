from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render
from apps.governance.models import ClubState, Role
from .permissions import capability_required, effective_role
from apps.members.selectors import own_profile, profile_data


def home(request):
    return render(request, "public/home.html")


@capability_required("account.access_private_area")
def dashboard(request):
    from apps.agenda.models import Registration
    from apps.agenda.selectors import upcoming_events, own_registration
    from apps.communications.models import Notification
    from apps.dues.models import DuesRecord
    state = ClubState.objects.select_related("active_year").first()
    role = effective_role(request.user)
    upcoming = []
    try:
        for event in list(upcoming_events(request.user))[:3]:
            upcoming.append({"event": event, "registration": own_registration(request.user, event)})
    except PermissionDenied:
        pass  # INVITE : aucune capacité event.register, calendrier omis sans erreur.
    current_dues = None
    if state and state.active_year:
        current_dues = DuesRecord.objects.filter(profile__user_id=request.user.pk, lions_year=state.active_year).first()
    return render(request, "espace/dashboard.html", {
        "effective_role_label": Role(role).label,
        "member": profile_data(request.user, own_profile(request.user), own=True),
        "active_year": state.active_year if state else None,
        "upcoming_events": upcoming,
        "unread_notifications": Notification.objects.filter(recipient=request.user, read_at__isnull=True).count(),
        "current_dues": current_dues,
    })


def robots(request):
    return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")
