from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
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
    from apps.satisfaction.selectors import open_periods, period_results
    from apps.governance.models import Mandate
    qs = scoped_profiles(request.user, management=True)
    to_regularize = DuesRecord.objects.filter(Q(tranche1_paid=False) | Q(tranche2_paid=False), lions_year=state.active_year).count() if state and state.active_year else 0
    open_votes = []
    for vote in Vote.objects.filter(status="OPEN"):
        elector_count = Elector.objects.filter(vote=vote).count()
        participation_count = Participation.objects.filter(elector__vote=vote).count()
        open_votes.append({"vote": vote, "elector_count": elector_count, "participation_count": participation_count,
            "rate": round(participation_count * 100 / elector_count, 1) if elector_count else 0})
    # Plusieurs consultations peuvent être ouvertes en même temps : la carte de synthèse
    # du tableau de bord n'en affiche qu'une (la plus récente) ; la liste complète reste
    # accessible via "Gestion satisfaction".
    satisfaction_period = open_periods(request.user).first()
    satisfaction_summary = period_results(request.user, satisfaction_period) if satisfaction_period else None
    return {
        "member_count": qs.count(), "active_count": qs.filter(status="ACTIVE", user__is_active=True).count(),
        "mandate_count": Mandate.objects.count(), "club_state": state, "to_regularize": to_regularize,
        "upcoming_events_count": Event.objects.filter(status="PUBLISHED", starts_at__gte=timezone.now()).count(),
        "document_count": Document.objects.filter(status="AVAILABLE").count(),
        "open_votes": open_votes, "satisfaction_period": satisfaction_period, "satisfaction_summary": satisfaction_summary,
    }


# Variante de composition du tableau de bord selon le rôle actif — décide uniquement de
# l'ordre/la présence des sections (voir espace/dashboard.html) ; le CONTENU de chaque
# section reste filtré par capability (can()), jamais par ce rôle directement. Un rôle
# ambigu (effective_role() -> None) retombe sur "member", le plus restreint.
_DASHBOARD_VARIANT_BY_ROLE = {
    Role.TRESORIER: "treasurer",
    Role.SECRETAIRE: "secretary",
    Role.PRESIDENT: "president",
    Role.PRESIDENT_FONDATEUR: "president",
    Role.SUPER_ADMIN: "president",
}
_DASHBOARD_INTRO = {
    "member": "Retrouvez vos prochaines actions et informations utiles.",
    "secretary": "Suivez l’activité quotidienne du club et les éléments à traiter.",
    "president": "Pilotez les activités du club et suivez les indicateurs essentiels.",
    "treasurer": "Suivez les cotisations et les encaissements de l’année Lions.",
}


def _dashboard_kpis(variant, overview, contact_pending_count):
    """4 KPI maximum, jamais une rangée de compteurs identiques par défaut — voir skill
    §1 et la consigne explicite de la refonte dashboard (pas de carte juste parce que la
    donnée existe)."""
    if variant == "president":
        return [
            {"icon": "members", "label": "Membres actifs", "value": overview["active_count"]},
            {"icon": "events", "label": "Événements à venir", "value": overview["upcoming_events_count"]},
            {"icon": "votes", "label": "Votes ouverts", "value": len(overview["open_votes"])},
            {"icon": "dues", "label": "Cotisations à régulariser", "value": overview["to_regularize"]},
        ]
    if variant == "secretary":
        kpis = [
            {"icon": "members", "label": "Membres actifs", "value": overview["active_count"]},
            {"icon": "events", "label": "Événements à venir", "value": overview["upcoming_events_count"]},
            {"icon": "documents", "label": "Documents disponibles", "value": overview["document_count"]},
        ]
        if contact_pending_count is not None:
            kpis.append({"icon": "contact", "label": "Messages en attente", "value": contact_pending_count})
        return kpis
    return []


def _dashboard_quicklinks(user, variant):
    """Chaque lien est conditionné par une capability réelle (can()), jamais par le rôle
    actif : un responsable désigné sans le rôle nominal, ou un rôle auquel une capacité a
    été retirée, ne voit jamais un lien qu'il ne peut pas utiliser."""
    candidates = {
        "president": [
            ("members.view_management", "Membres et mandats", "governance:members", None),
            ("year.manage", "Années Lions", "governance:years", None),
            ("document.manage", "Gérer les documents", "documents:manage_list", None),
            ("vote.manage", "Gérer les votes", "voting:manage_list", None),
            ("dues.manage", "Gérer les cotisations", "dues:manage_list", None),
            ("communication.send_member_broadcast", "Communication", "communications:broadcast", None),
            ("notification.send", "Envoyer une notification", "notifications:send", None),
        ],
        "secretary": [
            ("document.manage", "Gérer les documents", "documents:manage_list", None),
            ("event.register", "Calendrier", "agenda_private:calendar", None),
            ("contact.view", "Messages de contact", "communications:inbox", ["contact"]),
            ("communication.send_member_broadcast", "Communication", "communications:broadcast", None),
        ],
        "treasurer": [
            ("dues.manage", "Gérer les cotisations", "dues:manage_list", None),
            ("event.register", "Calendrier", "agenda_private:calendar", None),
            ("notification.view_own", "Notifications", "notifications:list", None),
        ],
    }
    links = []
    for capability, label, route, args in candidates.get(variant, []):
        if not can(user, capability):
            continue
        links.append({"label": label, "url": reverse(route, args=args) if args else reverse(route)})
    return links


@capability_required("account.access_private_area")
def dashboard(request):
    from apps.agenda.models import Registration
    from apps.agenda.selectors import upcoming_events, own_registration
    from apps.communications.models import Notification, ContactRequest
    from apps.dues.models import DuesRecord
    state = ClubState.objects.select_related("active_year").first()
    role = effective_role(request.user)
    variant = _DASHBOARD_VARIANT_BY_ROLE.get(role, "member")

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
        from apps.satisfaction.selectors import open_periods, own_response
        for period in open_periods(request.user):
            if not own_response(request.user, period):
                satisfaction_to_complete = period
                break
    except PermissionDenied:
        pass

    # Messages de contact en attente : compteur unique, réservé à qui a déjà accès à la
    # boîte de réception (contact.view) — jamais calculé, donc jamais affiché, sinon.
    contact_pending_count = ContactRequest.objects.filter(state="RECEIVED").count() if can(request.user, "contact.view") else None
    # La carte « À faire » n'apparaît qu'à qui peut traiter (contact.manage) : le Super
    # administrateur consulte la boîte sans que cela devienne une tâche pour lui.
    contact_to_process = contact_pending_count if can(request.user, "contact.manage") else None

    # Aperçu des dernières notifications : seulement sur le dashboard Membre (les autres
    # rôles gardent le compteur existant + CTA, déjà suffisant à leur échelle).
    recent_notifications = None
    if variant == "member":
        from apps.communications.private_views import resolve_target
        recent_notifications = [{"notification": n, "url": resolve_target(request.user, n)}
            for n in Notification.objects.filter(recipient=request.user)[:3]]

    # Documents récents : demandés explicitement pour Secrétaire, en option pour Membre.
    # Président/Trésorier n'en ont pas besoin sur leur dashboard (hors périmètre demandé).
    recent_documents = None
    if variant == "secretary":
        from apps.documents.models import Document as DocumentModel
        recent_documents = list(DocumentModel.objects.exclude(status=DocumentModel.Status.DELETED).order_by("-created_at")[:3])
    elif variant == "member":
        try:
            from apps.documents.selectors import scope_documents
            recent_documents = list(scope_documents(request.user).order_by("-created_at")[:3])
        except PermissionDenied:
            recent_documents = None

    dues_to_regularize = bool(current_dues and current_dues.status != "PAID")
    has_todo = bool(votes_to_complete or satisfaction_to_complete or contact_to_process or dues_to_regularize)

    context = {
        "effective_role_label": Role(role).label if role else None,
        "dashboard_variant": variant,
        "dashboard_intro": _DASHBOARD_INTRO[variant],
        "member": profile_data(request.user, own_profile(request.user), own=True),
        "active_year": state.active_year if state else None,
        "upcoming_events": upcoming,
        "unread_notifications": Notification.objects.filter(recipient=request.user, read_at__isnull=True).count(),
        "recent_notifications": recent_notifications,
        "current_dues": current_dues,
        "votes_to_complete": votes_to_complete,
        "satisfaction_to_complete": satisfaction_to_complete,
        "contact_pending_count": contact_to_process,
        "recent_documents": recent_documents,
        "dues_to_regularize": dues_to_regularize,
        "has_todo": has_todo,
    }
    if can(request.user, "management.access"):
        context.update(_management_overview(request, state))
        context["dashboard_kpis"] = _dashboard_kpis(variant, context, contact_pending_count)
    if can(request.user, "dues.manage"):
        from django.db.models import Q
        from apps.dues.selectors import collection_summary
        context["dues_collection"] = collection_summary(request.user, state.active_year if state else None)
        # Même requête que _management_overview (non applicable ici : le Trésorier n'a
        # pas management.access) — juste comptée séparément pour son propre dashboard.
        if state and state.active_year:
            context["dues_regularize_member_count"] = DuesRecord.objects.filter(
                Q(tranche1_paid=False) | Q(tranche2_paid=False), lions_year=state.active_year).count()
    if variant in ("president", "secretary", "treasurer"):
        context["dashboard_quicklinks"] = _dashboard_quicklinks(request.user, variant)
    return render(request, "espace/dashboard.html", context)


def robots(request):
    return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")
