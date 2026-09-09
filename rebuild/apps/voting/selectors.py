from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.http import Http404
from django.utils import timezone
from apps.core.permissions import can
from .models import Vote, Elector, Participation, Ballot, BallotSelection


def require(actor, capability, obj=None):
    if not can(actor, capability, obj):
        raise PermissionDenied


def votes_for_member(actor):
    require(actor, "vote.cast")
    profile = actor.member_profile
    vote_ids = Elector.objects.filter(profile=profile).values_list("vote_id", flat=True)
    return Vote.objects.filter(pk__in=vote_ids).exclude(status=Vote.Status.DRAFT)


def vote_for_member(actor, vote_id):
    try:
        return votes_for_member(actor).get(pk=vote_id)
    except Vote.DoesNotExist:
        raise Http404


def own_participation(actor, vote):
    try:
        elector = Elector.objects.get(vote=vote, profile__user_id=actor.pk)
    except Elector.DoesNotExist:
        return None
    return Participation.objects.filter(elector=elector).first()


def votes_for_manager(actor):
    require(actor, "vote.manage")
    return Vote.objects.all()


def vote_for_manager(actor, vote_id):
    try:
        return votes_for_manager(actor).get(pk=vote_id)
    except Vote.DoesNotExist:
        raise Http404


def tracking_rows(actor, vote):
    """Électeur + a voté / n'a pas voté. Jamais le choix : Participation ne contient aucun bulletin."""
    require(actor, "vote.manage")
    voted_ids = set(Participation.objects.filter(elector__vote=vote).values_list("elector_id", flat=True))
    electors = Elector.objects.filter(vote=vote).select_related("profile__user").order_by("profile__user__last_name", "profile__user__first_name")
    return [{"elector": elector, "voted": elector.pk in voted_ids} for elector in electors]


def can_view_results(actor, vote):
    if vote.status != Vote.Status.CLOSED:
        return False
    if can(actor, "vote.manage"):
        return True
    return Elector.objects.filter(vote=vote, profile__user_id=actor.pk).exists()


def vote_results(actor, vote):
    """Résultats seulement après clôture ; audience prudente = électeurs du scrutin (À CONFIRMER HUMAINEMENT)."""
    if not can_view_results(actor, vote):
        raise PermissionDenied
    elector_count = Elector.objects.filter(vote=vote).count()
    participation_count = Participation.objects.filter(elector__vote=vote).count()
    ballots = Ballot.objects.filter(vote=vote)
    ballot_count = ballots.count()
    blank_count = ballots.filter(is_blank=True).count()
    expressed = ballot_count - blank_count
    tallies = (BallotSelection.objects.filter(ballot__vote=vote).values("option_id", "option__label", "option__order")
        .annotate(votes=Count("id")).order_by("option__order"))
    options = [{
        "label": row["option__label"],
        "votes": row["votes"],
        # Convention : dénominateur = bulletins exprimés (non blancs). En choix multiple, la somme peut dépasser 100 %.
        "percentage": round(row["votes"] * 100 / expressed, 1) if expressed else 0,
        # Chaîne non localisée pour l'attribut CSS width (les chiffres visibles restent localisés).
        "percentage_width": f"{row['votes'] * 100 / expressed:.1f}" if expressed else "0",
    } for row in tallies]
    return {
        "elector_count": elector_count,
        "participation_count": participation_count,
        "participation_rate": round(participation_count * 100 / elector_count, 1) if elector_count else 0,
        "ballot_count": ballot_count,
        "expressed_count": expressed,
        "blank_count": blank_count,
        "options": options,
    }
