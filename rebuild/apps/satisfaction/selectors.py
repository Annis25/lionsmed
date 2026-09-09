from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count
from django.http import Http404
from django.utils import timezone
from apps.core.permissions import can
from .models import SatisfactionPeriod, SatisfactionResponse


def require(actor, capability, obj=None):
    if not can(actor, capability, obj):
        raise PermissionDenied


def current_period(actor):
    require(actor, "satisfaction.respond")
    now = timezone.now()
    return SatisfactionPeriod.objects.filter(opens_at__lte=now, closes_at__gt=now).first()


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


def period_results(actor, period):
    """Agrégats seulement : jamais de note ou de commentaire individuel exposé ici."""
    require(actor, "satisfaction.view_results")
    responses = SatisfactionResponse.objects.filter(period=period)
    count = responses.count()
    hidden = count < period.threshold
    if hidden:
        return {"count": count, "hidden": True, "threshold": period.threshold, "average": None, "distribution": None}
    average = responses.aggregate(avg=Avg("score"))["avg"]
    distribution = {row["score"]: row["total"] for row in responses.values("score").annotate(total=Count("id"))}
    return {"count": count, "hidden": False, "threshold": period.threshold, "average": round(average, 1) if average else None,
        "distribution": {score: distribution.get(score, 0) for score in range(1, 6)}}
