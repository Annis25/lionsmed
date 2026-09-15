from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404
from django.db.models import Q
from django.core.exceptions import ValidationError
from apps.core.permissions import can
from .models import DuesRecord, DuesSchedule


def require(actor, capability, obj=None):
    if not can(actor, capability, obj):
        raise PermissionDenied


def own_dues(actor):
    require(actor, "dues.view_own")
    return DuesRecord.objects.filter(profile__user_id=actor.pk).select_related("lions_year")


def dues_for_manager(actor, record_id):
    require(actor, "dues.view_management")
    try:
        return DuesRecord.objects.select_related("profile__user", "lions_year").get(pk=record_id)
    except DuesRecord.DoesNotExist:
        raise Http404


def dues_management_list(actor, params):
    require(actor, "dues.view_management")
    qs = DuesRecord.objects.select_related("profile__user", "lions_year").order_by("-lions_year__starts_on", "profile__user__last_name")
    year = params.get("year", "")
    status = params.get("status", "")
    if year:
        try:
            qs = qs.filter(lions_year_id=year)
        except (ValidationError, ValueError):
            raise Http404
    query = params.get("q", "").strip()[:150]
    for part in query.split():
        qs = qs.filter(Q(profile__user__first_name__icontains=part) | Q(profile__user__last_name__icontains=part))
    if status in ("PAID", "PARTIAL", "TO_REGULARIZE"):
        condition = {"PAID": Q(tranche1_paid=True, tranche2_paid=True),
            "PARTIAL": Q(tranche1_paid=True, tranche2_paid=False) | Q(tranche1_paid=False, tranche2_paid=True),
            "TO_REGULARIZE": Q(tranche1_paid=False, tranche2_paid=False)}[status]
        qs = qs.filter(condition)
    return Paginator(qs, 20).get_page(params.get("page"))


def schedule_for_year(lions_year):
    if not lions_year:
        return None
    return DuesSchedule.objects.filter(lions_year=lions_year).first()


def workspace_members(actor):
    """Tous les membres éligibles, indépendamment des filtres et de la pagination."""
    require(actor, "dues.view_management")
    from apps.members.models import MemberProfile
    from apps.core.permissions import DIRECTORY_ROLES, effective_role
    profiles = MemberProfile.objects.filter(status="ACTIVE", user__is_active=True).select_related("user").order_by("user__last_name", "user__first_name")
    return [profile for profile in profiles if effective_role(profile.user) in DIRECTORY_ROLES]


def collection_summary(actor, lions_year):
    """Estimation déclarative au barème actuel, pas un grand livre financier."""
    require(actor, "dues.manage")
    from decimal import Decimal
    summary = {"configured": False, "collected": None, "remaining": None,
               "expected": None, "member_count": 0, "rate": 0}
    if not lions_year:
        return summary
    members = workspace_members(actor)
    summary["member_count"] = len(members)
    schedule = schedule_for_year(lions_year)
    if not schedule or schedule.tranche1_amount is None or schedule.tranche2_amount is None:
        return summary
    records = DuesRecord.objects.filter(lions_year=lions_year, profile_id__in=[p.pk for p in members])
    collected = (schedule.tranche1_amount * records.filter(tranche1_paid=True).count()
                 + schedule.tranche2_amount * records.filter(tranche2_paid=True).count())
    expected = (schedule.tranche1_amount + schedule.tranche2_amount) * len(members)
    summary.update(configured=True, collected=collected, expected=expected,
                   remaining=expected-collected,
                   rate=round(collected * Decimal(100) / expected, 1) if expected else 0)
    return summary


def treasurer_workspace(actor, params, active_year):
    require(actor, "dues.view_management")
    from apps.governance.models import LionsYear
    year_id = params.get("year") or (active_year.pk if active_year else None)
    try:
        year = LionsYear.objects.get(pk=year_id) if year_id else None
    except (LionsYear.DoesNotExist, ValidationError, ValueError):
        raise Http404
    records = {r.profile_id: r for r in DuesRecord.objects.filter(lions_year=year)} if year else {}
    profiles = workspace_members(actor)
    rows, counts = [], {"paid": 0, "partial": 0, "unpaid": 0}
    query = params.get("q", "").strip().casefold()[:150]
    for profile in profiles:
        record = records.get(profile.pk)
        status = record.status if record else "TO_REGULARIZE"
        counts[{"PAID": "paid", "PARTIAL": "partial", "TO_REGULARIZE": "unpaid"}[status]] += 1
        if query and query not in profile.user.get_full_name().casefold():
            continue
        if params.get("status") in DuesRecord.STATUS_LABELS and status != params["status"]:
            continue
        rows.append({"profile": profile, "record": record, "status": status, "label": DuesRecord.STATUS_LABELS[status]})
    return year, counts, Paginator(rows, 20).get_page(params.get("page"))


def dues_badges(user_ids, lions_year):
    """{user_id: {"status": "PAID"|"PARTIAL"|"TO_REGULARIZE", "label": ...}} pour
    l'affichage en badge dans l'Annuaire et Membres et mandats — indexé par l'id du
    compte (User), comme les lignes produites par `profile_data()`. Aucune entrée pour
    un profil sans DuesRecord pour l'année active : absence de badge, jamais inventé."""
    if not lions_year:
        return {}
    records = DuesRecord.objects.filter(profile__user_id__in=user_ids, lions_year=lions_year).select_related("profile")
    return {r.profile.user_id: {"status": r.status, "label": r.status_label} for r in records}
