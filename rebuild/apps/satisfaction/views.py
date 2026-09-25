from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods, require_safe
from apps.core.permissions import capability_required, can
from .selectors import open_periods, own_response, periods_for_manager, period_for_manager, period_results, individual_responses
from .services import submit_satisfaction, create_period, update_period, add_axis, update_axis, delete_axis, move_axis
from .forms import SatisfactionForm, PeriodForm, AxisForm
from .models import SatisfactionAxis, SatisfactionPeriod


@capability_required("satisfaction.respond")
@require_http_methods(["GET", "POST"])
def respond(request):
    """Plusieurs consultations peuvent être ouvertes en même temps : un formulaire
    préfixé par période (Form(prefix=...)) évite toute collision de noms de champs
    entre elles sur une même page ; period_id (champ caché) identifie laquelle a été
    soumise."""
    submitted_id = request.POST.get("period_id") if request.method == "POST" else None
    entries = []
    for period in open_periods(request.user):
        response = own_response(request.user, period)
        is_submission = submitted_id == str(period.pk)
        form = SatisfactionForm(request.POST if is_submission else None, period=period, prefix=str(period.pk))
        if is_submission and not response and form.is_valid():
            try:
                submit_satisfaction(actor=request.user, period=period, score=form.cleaned_data["score"],
                    comment=form.cleaned_data["comment"],
                    axis_scores={axis.pk: form.cleaned_data[f"axis_{axis.pk}"] for axis in period.axes.all()})
                messages.success(request, "Merci, votre avis a été pris en compte.")
                return redirect("satisfaction:respond")
            except ValidationError as error:
                form.add_error(None, error)
        entries.append({"period": period, "response": response, "form": form})
    return render(request, "espace/satisfaction.html", {"entries": entries})


@capability_required("satisfaction.manage")
@require_http_methods(["GET", "POST"])
def manage_list(request):
    form = PeriodForm(request.POST or None, include_axes=True)
    if request.method == "POST" and form.is_valid():
        try:
            period = create_period(actor=request.user, opens_at=form.cleaned_data["opens_at"], closes_at=form.cleaned_data["closes_at"],
                threshold=form.cleaned_data["threshold"], title=form.cleaned_data["title"], description=form.cleaned_data["description"],
                axes=form.cleaned_data["axes"])
            messages.success(request, "Consultation et axes créés.")
            return redirect("satisfaction:edit", period.pk)
        except ValidationError as error:
            form.add_error(None, error)
    return render(request, "espace/satisfaction_gestion.html", {"periods": periods_for_manager(request.user), "form": form})


@capability_required("satisfaction.manage")
@require_http_methods(["GET", "POST"])
def edit(request, period_id):
    period = period_for_manager(request.user, period_id)
    has_responses = period.responses.exists()
    initial = {"title": period.title, "description": period.description, "threshold": period.threshold,
        "opens_at": period.opens_at, "closes_at": period.closes_at}
    form = PeriodForm(request.POST if request.method == "POST" else None, initial=initial)
    if has_responses:
        for name in ("opens_at", "closes_at", "threshold"):
            form.fields[name].disabled = True
    if request.method == "POST" and form.is_valid():
        try:
            update_period(actor=request.user, period=period, opens_at=form.cleaned_data["opens_at"], closes_at=form.cleaned_data["closes_at"],
                threshold=form.cleaned_data["threshold"], title=form.cleaned_data["title"], description=form.cleaned_data["description"])
            messages.success(request, "Consultation mise à jour.")
            return redirect("satisfaction:edit", period.pk)
        except ValidationError as error:
            form.add_error(None, error)
    return render(request, "espace/satisfaction_edit.html", {
        "period": period, "form": form, "axis_form": AxisForm(), "has_responses": has_responses,
        "axes": period.axes.all(),
    })


def _axis_or_404(period, axis_id):
    return get_object_or_404(SatisfactionAxis, pk=axis_id, period=period)


@capability_required("satisfaction.manage")
@require_http_methods(["POST"])
def axis_add(request, period_id):
    period = period_for_manager(request.user, period_id)
    form = AxisForm(request.POST)
    if form.is_valid():
        try:
            add_axis(actor=request.user, period=period, label=form.cleaned_data["label"])
            messages.success(request, "Axe ajouté.")
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
    else:
        messages.error(request, "Nom d’axe invalide.")
    return redirect("satisfaction:edit", period.pk)


@capability_required("satisfaction.manage")
@require_http_methods(["POST"])
def axis_edit(request, period_id, axis_id):
    period = period_for_manager(request.user, period_id)
    axis = _axis_or_404(period, axis_id)
    form = AxisForm(request.POST)
    if form.is_valid():
        try:
            update_axis(actor=request.user, axis=axis, label=form.cleaned_data["label"])
            messages.success(request, "Axe modifié.")
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
    else:
        messages.error(request, "Nom d’axe invalide.")
    return redirect("satisfaction:edit", period.pk)


@capability_required("satisfaction.manage")
@require_http_methods(["POST"])
def axis_delete(request, period_id, axis_id):
    period = period_for_manager(request.user, period_id)
    axis = _axis_or_404(period, axis_id)
    try:
        delete_axis(actor=request.user, axis=axis)
        messages.success(request, "Axe supprimé.")
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    return redirect("satisfaction:edit", period.pk)


@capability_required("satisfaction.manage")
@require_http_methods(["POST"])
def axis_move(request, period_id, axis_id):
    period = period_for_manager(request.user, period_id)
    axis = _axis_or_404(period, axis_id)
    direction = request.POST.get("direction")
    if direction in ("up", "down"):
        try:
            move_axis(actor=request.user, axis=axis, direction=direction)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
    return redirect("satisfaction:edit", period.pk)


@capability_required("satisfaction.view_results")
@require_safe
def results(request, period_id):
    period = get_object_or_404(SatisfactionPeriod, pk=period_id)
    return render(request, "espace/satisfaction_resultats.html", {"period": period, "results": period_results(request.user, period),
        "can_view_individual": can(request.user, "satisfaction.view_individual")})


@capability_required("satisfaction.view_individual")
@require_safe
def individual(request, period_id):
    period = get_object_or_404(SatisfactionPeriod, pk=period_id)
    return render(request, "espace/satisfaction_reponses.html", {"period": period, "rows": individual_responses(request.user, period)})
