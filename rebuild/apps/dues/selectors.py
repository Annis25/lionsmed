from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404
from apps.core.permissions import can
from .models import DuesRecord


def require(actor, capability, obj=None):
    if not can(actor, capability, obj):
        raise PermissionDenied


def own_dues(actor):
    require(actor, "dues.view_own")
    return DuesRecord.objects.filter(profile__user_id=actor.pk).select_related("lions_year")


def dues_for_manager(actor, record_id):
    require(actor, "dues.manage")
    try:
        return DuesRecord.objects.select_related("profile__user", "lions_year").get(pk=record_id)
    except DuesRecord.DoesNotExist:
        raise Http404


def dues_management_list(actor, params):
    require(actor, "dues.manage")
    qs = DuesRecord.objects.select_related("profile__user", "lions_year").order_by("-lions_year__starts_on", "profile__user__last_name")
    year = params.get("year", "")
    status = params.get("status", "")
    if year:
        qs = qs.filter(lions_year_id=year)
    if status in DuesRecord.Status.values:
        qs = qs.filter(status=status)
    return Paginator(qs, 20).get_page(params.get("page"))
