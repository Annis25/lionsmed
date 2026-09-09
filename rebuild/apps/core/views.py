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
    votes_to_complete = []
    try:
        from apps.voting.selectors import votes_for_member, own_participation
        for vote in votes_for_member(request.user).filter(status="OPEN"):
            if not own_participation(request.user, vote):
                votes_to_complete.append(vote)
    except PermissionDenied:
        pass  # INVITE : jamais électeur.
    satisfaction_to_complete = None
    try:
        from apps.satisfaction.selectors import current_period, own_response
        period = current_period(request.user)
        if period and not own_response(request.user, period):
            satisfaction_to_complete = period
    except PermissionDenied:
        pass
    return render(request, "espace/dashboard.html", {
        "effective_role_label": Role(role).label,
        "member": profile_data(request.user, own_profile(request.user), own=True),
        "active_year": state.active_year if state else None,
        "upcoming_events": upcoming,
        "unread_notifications": Notification.objects.filter(recipient=request.user, read_at__isnull=True).count(),
        "current_dues": current_dues,
        "votes_to_complete": votes_to_complete,
        "satisfaction_to_complete": satisfaction_to_complete,
    })


def robots(request):
    return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")
