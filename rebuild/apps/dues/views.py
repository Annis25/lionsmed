from django.contrib import messages
from django.core.exceptions import ValidationError, PermissionDenied
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_safe
from apps.core.permissions import capability_required, can
from apps.governance.models import LionsYear, ClubState
from .selectors import own_dues, dues_for_manager, schedule_for_year, treasurer_workspace, workspace_members
from .services import set_tranche_paid, set_dues_schedule, ensure_record
from .forms import ScheduleForm
from .models import DuesRecord


@capability_required("dues.view_own")
@require_safe
def own(request):
    state = ClubState.objects.select_related("active_year").first()
    schedule = schedule_for_year(state.active_year if state else None)
    return render(request, "espace/cotisations.html", {"records": own_dues(request.user), "schedule": schedule})


@capability_required("dues.view_management")
@require_safe
def manage_list(request):
    state = ClubState.objects.select_related("active_year").first()
    params = request.GET.copy()
    if "year" not in params and state and state.active_year:
        params["year"] = str(state.active_year_id)
    selected_year, counts, rows = treasurer_workspace(request.user, params, state.active_year if state else None)
    return render(request, "espace/dues_management.html", {
        "page_obj": rows, "counts": counts, "selected_year": selected_year,
        "years": LionsYear.objects.all(),
        "statuses": DuesRecord.STATUS_LABELS.items(),
        "schedule": schedule_for_year(state.active_year if state else None),
        "active_year": state.active_year if state else None,
        "can_edit": can(request.user, "dues.manage"),
        "member_suggestions": sorted({profile.user.get_full_name() for profile in workspace_members(request.user) if profile.user.get_full_name()}),
    })


@capability_required("dues.manage")
@require_http_methods(["POST"])
def manage_set(request, year_id, profile_id, tranche):
    from apps.members.models import MemberProfile
    from .forms import TranchePaymentForm
    year = get_object_or_404(LionsYear, pk=year_id)
    profile = get_object_or_404(MemberProfile, pk=profile_id, status="ACTIVE", user__is_active=True)
    from apps.core.permissions import DIRECTORY_ROLES, effective_role
    if effective_role(profile.user) not in DIRECTORY_ROLES or tranche not in (1, 2):
        raise PermissionDenied
    form = TranchePaymentForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Paiement invalide : vérifiez l’état et la date.")
    else:
        record = ensure_record(actor=request.user, profile=profile, lions_year=year)
        set_tranche_paid(actor=request.user, record=record, tranche=tranche, **form.cleaned_data)
        messages.success(request, "Cotisation enregistrée.")
    from django.urls import reverse
    return redirect(reverse("dues:manage_list") + f"?year={year.pk}")


@capability_required("dues.manage")
@require_http_methods(["POST"])
def manage_toggle_tranche(request, record_id, tranche):
    record = dues_for_manager(request.user, record_id)
    if tranche not in (1, 2):
        raise PermissionDenied
    try:
        set_tranche_paid(actor=request.user, record=record, tranche=tranche,
            paid=not getattr(record, f"tranche{tranche}_paid"))
        messages.success(request, "Tranche mise à jour.")
    except (ValidationError, PermissionDenied) as error:
        messages.error(request, " ".join(error.messages) if hasattr(error, "messages") else str(error))
    referer = request.META.get("HTTP_REFERER", "")
    if not url_has_allowed_host_and_scheme(referer, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        referer = ""
    return redirect(referer or "dues:manage_list")


@capability_required("dues.view_management")
@require_safe
def manage_detail(request, record_id):
    record = dues_for_manager(request.user, record_id)
    return render(request, "espace/dues_detail.html", {"record": record, "changes": record.changes.select_related("actor"),
        "can_edit": can(request.user, "dues.manage")})


@capability_required("dues.manage")
@require_http_methods(["GET", "POST"])
def manage_schedule(request):
    state = ClubState.objects.select_related("active_year").first()
    if not state or not state.active_year:
        messages.error(request, "Aucune Année Lions active : configurez-en une avant de fixer les montants.")
        return redirect("dues:manage_list")
    schedule = schedule_for_year(state.active_year)
    edit = request.GET.get("edit") == "1" or request.method == "POST"
    form = ScheduleForm(request.POST or None, initial={
        "tranche1_amount": schedule.tranche1_amount if schedule else None,
        "tranche2_amount": schedule.tranche2_amount if schedule else None,
    })
    if request.method == "POST" and form.is_valid():
        try:
            set_dues_schedule(actor=request.user, lions_year=state.active_year,
                tranche1_amount=form.cleaned_data["tranche1_amount"], tranche2_amount=form.cleaned_data["tranche2_amount"])
            messages.success(request, "Montants mis à jour.")
            return redirect("dues:manage_list")
        except ValidationError as error:
            form.add_error(None, error)
    return render(request, "espace/dues_schedule.html", {"form": form, "schedule": schedule, "edit": edit, "active_year": state.active_year})
