from django.contrib import messages
from django.core.exceptions import ValidationError, PermissionDenied
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods, require_safe
from apps.core.permissions import capability_required, can
from apps.governance.models import LionsYear, ClubState
from .selectors import own_dues, dues_for_manager, dues_management_list, schedule_for_year
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
    return render(request, "espace/dues_management.html", {
        "page_obj": dues_management_list(request.user, request.GET),
        "years": LionsYear.objects.all(),
        "statuses": DuesRecord.STATUS_LABELS.items(),
        "schedule": schedule_for_year(state.active_year if state else None),
        "active_year": state.active_year if state else None,
        "can_edit": can(request.user, "dues.manage"),
    })


@capability_required("dues.manage")
@require_http_methods(["POST"])
def manage_toggle_tranche(request, record_id, tranche):
    record = dues_for_manager(request.user, record_id)
    try:
        set_tranche_paid(actor=request.user, record=record, tranche=tranche,
            paid=not getattr(record, f"tranche{tranche}_paid"))
        messages.success(request, "Tranche mise à jour.")
    except (ValidationError, PermissionDenied) as error:
        messages.error(request, " ".join(error.messages) if hasattr(error, "messages") else str(error))
    return redirect(request.META.get("HTTP_REFERER") or "dues:manage_list")


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
