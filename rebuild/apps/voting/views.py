from uuid import UUID
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods, require_safe
from apps.core.permissions import capability_required, can
from apps.members.selectors import directory_page, member_profile
from .models import Vote, VoteOption
from .selectors import votes_for_member, vote_for_member, own_participation, votes_for_manager, vote_for_manager, tracking_rows, vote_results, can_view_results, require, nominative_rows
from .services import (add_option, remove_option, open_vote, close_vote, cast_vote,
    create_and_open_vote, set_vote_manager, validate_vote_selection)
from .forms import VoteForm, VoteOptionForm


def _vote_row(actor, vote):
    """Un vote, sa participation éventuelle et si le lien résultats est autorisé —
    calculé ici pour que le template n'ait jamais à décider seul d'afficher ce lien
    (respect strict des permissions existantes, voir can_view_results)."""
    return {"vote": vote, "participation": own_participation(actor, vote),
        "can_view_results": vote.status == Vote.Status.CLOSED and can_view_results(actor, vote)}


@capability_required("vote.cast")
@require_safe
def member_list(request):
    votes = [_vote_row(request.user, vote) for vote in votes_for_member(request.user)]
    open_count = sum(1 for row in votes if row["vote"].status == Vote.Status.OPEN)
    closed_count = sum(1 for row in votes if row["vote"].status == Vote.Status.CLOSED)
    return render(request, "espace/votes.html", {
        "votes": votes, "open_count": open_count, "closed_count": closed_count,
    })


def _parse_choices(request):
    raw = request.POST.getlist("options")
    ids = []
    for value in raw:
        try:
            ids.append(UUID(value))
        except ValueError:
            raise Http404
    return ids


def _parse_member_selection(request, vote):
    """Le choix unique partage un seul groupe radio, vote blanc compris."""
    if vote.mode != Vote.Mode.MULTIPLE:
        value = request.POST.get("ballot_choice", "")
        legacy_ids = _parse_choices(request)
        legacy_blank = request.POST.get("blank") == "1"
        if value == "__blank__":
            return legacy_ids, True
        if value:
            try:
                return [UUID(value), *legacy_ids], legacy_blank
            except ValueError:
                raise Http404
        # Compatibilité avec un formulaire déjà ouvert avant le déploiement : le
        # serveur conserve l'ancien format, mais applique la même validation stricte.
        return legacy_ids, legacy_blank
    return _parse_choices(request), request.POST.get("blank") == "1"


@capability_required("vote.cast")
@require_http_methods(["GET", "POST"])
def member_detail(request, vote_id):
    vote = vote_for_member(request.user, vote_id)
    participation = own_participation(request.user, vote)
    if request.method == "POST" and vote.status == "OPEN" and not participation:
        option_ids, is_blank = _parse_member_selection(request, vote)
        try:
            option_ids = validate_vote_selection(vote=vote, option_ids=option_ids, is_blank=is_blank)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
            return redirect("voting:member_detail", vote_id=vote.pk)
        options = list(VoteOption.objects.filter(pk__in=option_ids, vote=vote))
        return render(request, "espace/vote_confirm.html", {
            "vote": vote, "options": options, "is_blank": is_blank,
            "option_ids": [str(o) for o in option_ids],
        })
    other_votes = [_vote_row(request.user, other) for other in votes_for_member(request.user).exclude(pk=vote.pk)]
    return render(request, "espace/votes.html", {
        "votes": [_vote_row(request.user, vote)], "single": True, "other_votes": other_votes,
    })


@capability_required("vote.cast")
@require_http_methods(["POST"])
def member_confirm(request, vote_id):
    vote = vote_for_member(request.user, vote_id)
    option_ids = _parse_choices(request)
    is_blank = request.POST.get("blank") == "1"
    try:
        cast_vote(actor=request.user, vote=vote, option_ids=option_ids, is_blank=is_blank)
        messages.success(request, "Votre bulletin a été enregistré. Il est définitif et ne peut plus être modifié.")
    except ValidationError as error:
        messages.error(request, " ".join(error.messages) if hasattr(error, "messages") else str(error))
    except PermissionDenied:
        raise
    return redirect("voting:member_list")


@capability_required("vote.view_results")
@require_safe
def results(request, vote_id):
    vote = get_object_or_404(Vote, pk=vote_id)
    if not can_view_results(request.user, vote):
        raise PermissionDenied
    results_data = vote_results(request.user, vote)
    leading_votes = max((option["votes"] for option in results_data["options"]), default=0)
    leading_option = next((o for o in results_data["options"] if o["votes"] == leading_votes and leading_votes > 0), None)
    return render(request, "espace/vote_resultats.html", {
        "vote": vote, "results": results_data, "leading_votes": leading_votes, "leading_option": leading_option,
        "can_manage": can(request.user, "vote.manage"),
        "can_view_nominative": vote.disclosure == Vote.Disclosure.NOMINATIVE and can(request.user, "vote.view_nominative"),
    })


@capability_required("vote.view_nominative")
@require_safe
def nominative(request, vote_id):
    vote = get_object_or_404(Vote, pk=vote_id)
    return render(request, "espace/vote_nominatif.html", {"vote": vote, "rows": nominative_rows(request.user, vote)})


@capability_required("vote.manage")
@require_safe
def manage_list(request):
    from django.db.models import Count
    votes = list(votes_for_manager(request.user).annotate(ballot_count=Count("ballots")))
    counts = {"OPEN": 0, "CLOSED": 0, "DRAFT": 0}
    for vote in votes:
        counts[vote.status] = counts.get(vote.status, 0) + 1
    return render(request, "espace/votes_gestion.html", {
        "votes": votes, "open_count": counts["OPEN"], "closed_count": counts["CLOSED"], "draft_count": counts["DRAFT"],
    })


@capability_required("vote.manage")
@require_http_methods(["GET", "POST"])
def manage_create(request):
    from uuid import uuid4
    form = VoteForm(request.POST or None, initial={"creation_key": uuid4()})
    option_labels = request.POST.getlist("options") if request.method == "POST" else ["", ""]
    if request.method == "POST" and form.is_valid():
        try:
            vote = create_and_open_vote(actor=request.user, option_labels=option_labels, **form.cleaned_data)
            messages.success(request, "Scrutin créé et ouvert : il est immédiatement partagé avec tous les électeurs.")
            from .notifications import notify_vote_opened
            notify_vote_opened(vote)
            return redirect("voting:manage_track", vote_id=vote.pk)
        except ValidationError as error:
            form.add_error(None, error)
    return render(request, "espace/vote_creation.html", {"form": form, "option_labels": option_labels})


@capability_required("vote.manage")
@require_http_methods(["GET", "POST"])
def manage_detail(request, vote_id):
    vote = vote_for_manager(request.user, vote_id)
    form = VoteOptionForm(request.POST or None)
    if request.method == "POST" and vote.status == Vote.Status.DRAFT and form.is_valid():
        try:
            add_option(actor=request.user, vote=vote, label=form.cleaned_data["label"],
                presentation=form.cleaned_data["presentation"], photo=form.cleaned_data["photo"])
            return redirect("voting:manage_detail", vote_id=vote.pk)
        except ValidationError as error:
            form.add_error(None, error)
    return render(request, "espace/vote_creation.html", {"form": form, "vote": vote, "options": vote.options.all()})


@capability_required("vote.manage")
@require_http_methods(["POST"])
def manage_option_remove(request, vote_id, option_id):
    vote = vote_for_manager(request.user, vote_id)
    option = get_object_or_404(VoteOption, pk=option_id, vote=vote)
    try:
        remove_option(actor=request.user, option=option)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    return redirect("voting:manage_detail", vote_id=vote.pk)


@capability_required("vote.manage")
@require_http_methods(["POST"])
def manage_open(request, vote_id):
    vote = vote_for_manager(request.user, vote_id)
    try:
        open_vote(actor=request.user, vote=vote)
        messages.success(request, "Scrutin ouvert. Les électeurs sont figés.")
        from .notifications import notify_vote_opened
        notify_vote_opened(vote)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    return redirect("voting:manage_track", vote_id=vote.pk)


@capability_required("vote.manage")
@require_safe
def manage_track(request, vote_id):
    vote = vote_for_manager(request.user, vote_id)
    return render(request, "espace/vote_suivi.html", {"vote": vote, "rows": tracking_rows(request.user, vote),
        "can_view_nominative": vote.disclosure == Vote.Disclosure.NOMINATIVE and can(request.user, "vote.view_nominative")})


@capability_required("management.access")
@require_safe
def manage_responsibles(request):
    from apps.members.models import MemberProfile
    from apps.governance.models import Role
    page = directory_page(request.user, request.GET, management=True)
    designated_ids = set(MemberProfile.objects.filter(is_vote_manager=True).values_list("user_id", flat=True))
    for row in page.object_list:
        row["is_vote_manager"] = row["id"] in designated_ids
    current = MemberProfile.objects.filter(is_vote_manager=True).select_related("user").order_by("user__last_name", "user__first_name")
    return render(request, "espace/vote_responsables.html", {"page_obj": page, "current": current, "roles": Role.choices})


@capability_required("management.access")
@require_http_methods(["POST"])
def manage_responsible_toggle(request, user_id):
    profile = member_profile(request.user, user_id, management=True)
    enabled = request.POST.get("action") == "designer"
    try:
        set_vote_manager(actor=request.user, profile=profile, enabled=enabled)
        messages.success(request, "Responsable de vote désigné." if enabled else "Responsabilité de vote retirée.")
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    return redirect("voting:manage_responsibles")


@capability_required("vote.manage")
@require_http_methods(["POST"])
def manage_close(request, vote_id):
    vote = vote_for_manager(request.user, vote_id)
    try:
        close_vote(actor=request.user, vote=vote)
        messages.success(request, "Scrutin clôturé. Les résultats sont désormais accessibles aux électeurs.")
        from .notifications import notify_vote_closed
        notify_vote_closed(vote)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    return redirect("voting:manage_track", vote_id=vote.pk)
