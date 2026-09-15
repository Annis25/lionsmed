from datetime import date
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction, IntegrityError
from django.utils import timezone
from apps.core.permissions import can
from apps.core.models import AuditEvent
from .models import SatisfactionPeriod, SatisfactionResponse, SatisfactionAxis, SatisfactionAxisScore
from .scheduling import compute_auto_window

RULE_VERSION = "phase-b-v1"


def require(actor, capability, obj=None):
    if not can(actor, capability, obj):
        raise PermissionDenied


def audit(actor, action, obj):
    # Jamais de note ni de commentaire : uniquement type/identifiant d'objet.
    AuditEvent.objects.create(actor=actor, action=action, object_type=obj._meta.object_name, object_id=str(obj.pk))


@transaction.atomic
def open_period(*, actor, year, month, threshold, auto_schedule=False, opens_at=None, closes_at=None, title=None, description=None, axes=None):
    require(actor, "satisfaction.manage")
    if auto_schedule:
        opens_at, closes_at = compute_auto_window(year, month)
        if opens_at is None:
            raise ValidationError("Heure de référence non configurée : activation automatique impossible.")
    else:
        if not opens_at or not closes_at:
            raise ValidationError("Date et heure de lancement et de fermeture requises hors activation automatique.")
        if closes_at <= opens_at:
            raise ValidationError("La fermeture doit être postérieure au lancement.")
    period, created = SatisfactionPeriod.objects.get_or_create(
        month=date(year, month, 1), defaults={"created_by": actor, "rule_version": RULE_VERSION})
    if not created:
        period = SatisfactionPeriod.objects.select_for_update().get(pk=period.pk)
    labels = [line.strip() for line in axes.splitlines() if line.strip()] if axes is not None else None
    if labels is not None and (len(labels) > 30 or any(len(label) > 180 for label in labels)):
        raise ValidationError("Au maximum 30 axes, de 180 caractères chacun.")
    has_responses = period.responses.exists()
    if has_responses and labels is not None and labels != list(period.axes.values_list("label", flat=True)):
        raise ValidationError("Des réponses existent : les axes sont figés. Le titre et la description restent modifiables.")
    if has_responses and (period.opens_at != opens_at or period.closes_at != closes_at or period.threshold != threshold):
        raise ValidationError("Des réponses existent : dates et seuil de confidentialité sont figés.")
    if title is not None:
        period.title = title
    if description is not None:
        period.description = description
    period.rule_version = RULE_VERSION
    period.opens_at = opens_at
    period.closes_at = closes_at
    period.threshold = threshold
    period.full_clean()
    period.save()
    if labels is not None and not has_responses:
        period.axes.all().delete()
        SatisfactionAxis.objects.bulk_create([SatisfactionAxis(period=period, label=label, order=i) for i, label in enumerate(labels)])
    audit(actor, "satisfaction.period_configured", period)
    return period


@transaction.atomic
def submit_satisfaction(*, actor, period, score, comment="", axis_scores=None):
    require(actor, "satisfaction.respond")
    if score not in range(1, 6):
        raise ValidationError("Note invalide (1 à 5).")
    period = SatisfactionPeriod.objects.select_for_update().get(pk=period.pk)
    axes = list(period.axes.all())
    axis_scores = axis_scores or {}
    if set(axis_scores) != {axis.pk for axis in axes} or any(value not in range(1, 6) for value in axis_scores.values()):
        raise ValidationError("Veuillez noter chaque axe de 1 à 5.")
    now = timezone.now()
    if not period.opens_at or not period.closes_at or not (period.opens_at <= now < period.closes_at):
        raise ValidationError("Cette période n'est pas ouverte.")
    profile = actor.member_profile
    if SatisfactionResponse.objects.filter(period=period, profile=profile).exists():
        raise ValidationError("Une réponse a déjà été enregistrée pour cette période.")
    response = SatisfactionResponse(period=period, profile=profile, score=score, comment=comment[:1000])
    try:
        response.full_clean()
        response.save()
        SatisfactionAxisScore.objects.bulk_create([SatisfactionAxisScore(response=response, axis=axis, score=axis_scores[axis.pk]) for axis in axes])
    except IntegrityError:
        raise ValidationError("Une réponse a déjà été enregistrée pour cette période.")
    audit(actor, "satisfaction.responded", response)
    return response
