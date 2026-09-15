from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods, require_safe
from apps.core.permissions import capability_required
from .selectors import current_period, own_response, periods_for_manager, period_results
from .services import submit_satisfaction, open_period
from .forms import SatisfactionForm, PeriodOpenForm
from .models import SatisfactionPeriod


@capability_required("satisfaction.respond")
@require_http_methods(["GET", "POST"])
def respond(request):
    period = current_period(request.user)
    response = own_response(request.user, period)
    form = SatisfactionForm(request.POST or None, period=period)
    if request.method == "POST" and period and not response and form.is_valid():
        try:
            submit_satisfaction(actor=request.user, period=period, score=form.cleaned_data["score"], comment=form.cleaned_data["comment"], axis_scores={axis.pk: form.cleaned_data[f"axis_{axis.pk}"] for axis in period.axes.all()})
            messages.success(request, "Merci, votre avis a été pris en compte.")
            return redirect("satisfaction:respond")
        except ValidationError as error:
            form.add_error(None, error)
    return render(request, "espace/satisfaction.html", {"period": period, "response": response, "form": form})


@capability_required("satisfaction.manage")
@require_http_methods(["GET", "POST"])
def manage_list(request):
    form = PeriodOpenForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            period = open_period(actor=request.user, year=form.cleaned_data["year"], month=form.cleaned_data["month"],
                threshold=form.cleaned_data["threshold"], auto_schedule=form.cleaned_data["auto_schedule"],
                opens_at=form.cleaned_data["opens_at"], closes_at=form.cleaned_data["closes_at"], title=form.cleaned_data["title"], description=form.cleaned_data["description"], axes=form.cleaned_data["axes"])
            from .notifications import notify_period_opened
            notify_period_opened(period)
            messages.success(request, "Période configurée.")
            return redirect("satisfaction:manage_list")
        except ValidationError as error:
            form.add_error(None, error)
    return render(request, "espace/satisfaction_gestion.html", {"periods": periods_for_manager(request.user), "form": form})


@capability_required("satisfaction.manage")
@require_http_methods(["GET", "POST"])
def edit(request, period_id):
    period = get_object_or_404(SatisfactionPeriod, pk=period_id)
    initial = {"year": period.month.year, "month": period.month.month, "title": period.title,
        "description": period.description, "threshold": period.threshold, "auto_schedule": False,
        "opens_at": period.opens_at, "closes_at": period.closes_at,
        "axes": "\n".join(period.axes.values_list("label", flat=True))}
    form = PeriodOpenForm(request.POST or None, initial=initial)
    form.fields["year"].disabled = form.fields["month"].disabled = True
    if period.responses.exists():
        for name in ("axes", "opens_at", "closes_at", "threshold", "auto_schedule"):
            form.fields[name].disabled = True
    if request.method == "POST" and form.is_valid():
        try:
            open_period(actor=request.user, **form.cleaned_data)
            messages.success(request, "Consultation modifiée.")
            return redirect("satisfaction:manage_list")
        except ValidationError as error:
            form.add_error(None, error)
    return render(request, "espace/satisfaction_edit.html", {"period": period, "form": form})


@capability_required("satisfaction.view_results")
@require_safe
def results(request, period_id):
    period = get_object_or_404(SatisfactionPeriod, pk=period_id)
    return render(request, "espace/satisfaction_resultats.html", {"period": period, "results": period_results(request.user, period)})
