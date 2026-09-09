from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods, require_safe
from apps.core.permissions import capability_required
from apps.governance.models import LionsYear
from .selectors import own_dues, dues_for_manager, dues_management_list
from .services import record_dues_status
from .forms import DuesUpdateForm
from .models import DuesRecord


@capability_required("dues.view_own")
@require_safe
def own(request):
    return render(request, "espace/cotisations.html", {"records": own_dues(request.user)})


@capability_required("dues.manage")
@require_safe
def manage_list(request):
    return render(request, "espace/dues_management.html", {
        "page_obj": dues_management_list(request.user, request.GET),
        "years": LionsYear.objects.all(),
        "statuses": DuesRecord.Status.choices,
    })


@capability_required("dues.manage")
@require_http_methods(["GET", "POST"])
def manage_detail(request, record_id):
    record = dues_for_manager(request.user, record_id)
    if request.method == "POST":
        form = DuesUpdateForm(request.POST)
        if form.is_valid():
            try:
                record_dues_status(actor=request.user, record=record, status=form.cleaned_data["status"],
                    amount=form.cleaned_data["amount"], paid_on=form.cleaned_data["paid_on"], motif=form.cleaned_data["motif"])
                messages.success(request, "Cotisation mise à jour.")
                return redirect("dues:manage_detail", record_id=record.pk)
            except ValidationError as error:
                form.add_error(None, error)
    else:
        form = DuesUpdateForm(initial={"status": record.status, "amount": record.amount, "paid_on": record.paid_on})
    return render(request, "espace/dues_detail.html", {"record": record, "form": form, "changes": record.changes.select_related("actor")})
