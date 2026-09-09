from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from apps.governance.models import ClubState, Role
from .permissions import capability_required, effective_role, can
from apps.members.selectors import own_profile, profile_data, scoped_profiles


def home(request):
    return render(request, "public/home.html")


def _management_overview(request, state):
    from django.db.models import Q
    from apps.dues.models import DuesRecord
    from apps.agenda.models import Event
    from apps.documents.models import Document
    from apps.voting.models import Vote, Elector, Participation
    from apps.satisfaction.selectors import current_period, period_results
    from apps.governance.models import Mandate
    qs = scoped_profiles(request.user, management=True)
    to_regularize = DuesRecord.objects.filter(Q(tranche1_paid=False) | Q(tranche2_paid=False), lions_year=state.active_year).count() if state and state.active_year else 0
    open_votes = []
    for vote in Vote.objects.filter(status="OPEN"):
        elector_count = Elector.objects.filter(vote=vote).count()
        participation_count = Participation.objects.filter(elector__vote=vote).count()
        open_votes.append({"vote": vote, "elector_count": elector_count, "participation_count": participation_count,
            "rate": round(participation_count * 100 / elector_count, 1) if elector_count else 0})
    satisfaction_period = current_period(request.user)
    satisfaction_summary = period_results(request.user, satisfaction_period) if satisfaction_period else None
    return {
        "member_count": qs.count(), "active_count": qs.filter(status="ACTIVE", user__is_active=True).count(),
        "mandate_count": Mandate.objects.count(), "club_state": state, "to_regularize": to_regularize,
        "upcoming_events_count": Event.objects.filter(status="PUBLISHED", starts_at__gte=timezone.now()).count(),
        "document_count": Document.objects.filter(status="AVAILABLE").count(),
        "open_votes": open_votes, "satisfaction_period": satisfaction_period, "satisfaction_summary": satisfaction_summary,
    }


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
    context = {
        "effective_role_label": Role(role).label,
        "member": profile_data(request.user, own_profile(request.user), own=True),
        "active_year": state.active_year if state else None,
        "upcoming_events": upcoming,
        "unread_notifications": Notification.objects.filter(recipient=request.user, read_at__isnull=True).count(),
        "current_dues": current_dues,
        "votes_to_complete": votes_to_complete,
        "satisfaction_to_complete": satisfaction_to_complete,
    }
    if can(request.user, "management.access"):
        context.update(_management_overview(request, state))
    return render(request, "espace/dashboard.html", context)


def robots(request):
    return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")
