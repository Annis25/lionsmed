from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404
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
        qs = qs.filter(lions_year_id=year)
    page = Paginator(qs, 20).get_page(params.get("page"))
    if status in ("PAID", "PARTIAL", "TO_REGULARIZE"):
        page.object_list = [r for r in page.object_list if r.status == status]
    return page


def schedule_for_year(lions_year):
    if not lions_year:
        return None
    return DuesSchedule.objects.filter(lions_year=lions_year).first()


def dues_badges(user_ids, lions_year):
    """{user_id: {"status": "PAID"|"PARTIAL"|"TO_REGULARIZE", "label": ...}} pour
    l'affichage en badge dans l'Annuaire et Membres et mandats — indexé par l'id du
    compte (User), comme les lignes produites par `profile_data()`. Aucune entrée pour
    un profil sans DuesRecord pour l'année active : absence de badge, jamais inventé."""
    if not lions_year:
        return {}
    records = DuesRecord.objects.filter(profile__user_id__in=user_ids, lions_year=lions_year).select_related("profile")
    return {r.profile.user_id: {"status": r.status, "label": r.status_label} for r in records}
