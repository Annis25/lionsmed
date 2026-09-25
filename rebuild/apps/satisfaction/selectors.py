from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count
from django.http import Http404
from django.utils import timezone
from apps.core.permissions import can, effective_role, MEMBERS
from .models import SatisfactionPeriod, SatisfactionResponse


def require(actor, capability, obj=None):
    if not can(actor, capability, obj):
        raise PermissionDenied


def open_periods(actor):
    """Toutes les consultations actuellement ouvertes — plusieurs peuvent l'être en
    même temps depuis que `month` n'est plus une contrainte d'unicité."""
    require(actor, "satisfaction.respond")
    now = timezone.now()
    return SatisfactionPeriod.objects.filter(opens_at__lte=now, closes_at__gt=now).order_by("-opens_at")


def own_response(actor, period):
    if period is None:
        return None
    return SatisfactionResponse.objects.filter(period=period, profile__user_id=actor.pk).first()


def period_for_manager(actor, period_id):
    require(actor, "satisfaction.manage")
    try:
        return SatisfactionPeriod.objects.get(pk=period_id)
    except SatisfactionPeriod.DoesNotExist:
        raise Http404


def periods_for_manager(actor):
    require(actor, "satisfaction.manage")
    return SatisfactionPeriod.objects.all()


def eligible_respondents_count():
    """Membres actuellement en mesure de répondre (satisfaction.respond) : approximation
    au jour de la consultation, jamais un effectif figé au moment de l'ouverture — les
    entrées/sorties de membres depuis la période concernée ne sont pas reconstituées."""
    from apps.members.models import MemberProfile
    profiles = MemberProfile.objects.filter(status=MemberProfile.Status.ACTIVE, user__is_active=True).select_related("user")
    return sum(1 for profile in profiles if effective_role(profile.user) in MEMBERS)


def period_results(actor, period):
    """Agrégats seulement : jamais de note ou de commentaire individuel exposé ici."""
    require(actor, "satisfaction.view_results")
    responses = SatisfactionResponse.objects.filter(period=period)
    count = responses.count()
    hidden = count < period.threshold
    if hidden:
        return {"count": count, "hidden": True, "threshold": period.threshold, "average": None, "distribution": None,
            "participation_rate": None, "eligible_count": None}
    average = responses.aggregate(avg=Avg("score"))["avg"]
    distribution = {row["score"]: row["total"] for row in responses.values("score").annotate(total=Count("id"))}
    axes = []
    for axis in period.axes.all():
        stats = axis.scores.aggregate(average=Avg("score"), count=Count("id"))
        if stats["count"] >= period.threshold:
            axes.append({"label": axis.label, "average": round(stats["average"], 1), "count": stats["count"]})
    eligible = eligible_respondents_count()
    return {"axes": axes, "count": count, "hidden": False, "threshold": period.threshold, "average": round(average, 1) if average else None,
        "distribution": {score: distribution.get(score, 0) for score in range(1, 6)},
        "eligible_count": eligible, "participation_rate": round(100 * count / eligible, 1) if eligible else None}


def individual_responses(actor, period):
    """Réponses nominatives d'une consultation — Super administrateur uniquement
    (satisfaction.view_individual). Aucun seuil : c'est précisément une vue par personne."""
    require(actor, "satisfaction.view_individual")
    axes = list(period.axes.all())
    rows = []
    for response in (SatisfactionResponse.objects.filter(period=period).select_related("profile__user")
                     .prefetch_related("axis_scores").order_by("profile__user__last_name", "profile__user__first_name", "submitted_at")):
        scores = {item.axis_id: item.score for item in response.axis_scores.all()}
        user = response.profile.user
        rows.append({"name": user.get_full_name().strip() or user.email, "score": response.score,
            "axes": [{"label": axis.label, "score": scores.get(axis.pk)} for axis in axes],
            "comment": response.comment, "submitted_at": response.submitted_at})
    return rows
