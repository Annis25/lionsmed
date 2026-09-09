from datetime import date
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction, IntegrityError
from django.utils import timezone
from apps.core.permissions import can
from apps.core.models import AuditEvent
from .models import SatisfactionPeriod, SatisfactionResponse
from .scheduling import compute_auto_window

RULE_VERSION = "phase-b-v1"


def require(actor, capability, obj=None):
    if not can(actor, capability, obj):
        raise PermissionDenied


def audit(actor, action, obj):
    # Jamais de note ni de commentaire : uniquement type/identifiant d'objet.
    AuditEvent.objects.create(actor=actor, action=action, object_type=obj._meta.object_name, object_id=str(obj.pk))


@transaction.atomic
def open_period(*, actor, year, month, threshold, auto_schedule=False, opens_at=None, closes_at=None):
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
    period.rule_version = RULE_VERSION
    period.opens_at = opens_at
    period.closes_at = closes_at
    period.threshold = threshold
    period.full_clean()
    period.save()
    audit(actor, "satisfaction.period_configured", period)
    return period


@transaction.atomic
def submit_satisfaction(*, actor, period, score, comment=""):
    require(actor, "satisfaction.respond")
    if score not in range(1, 6):
        raise ValidationError("Note invalide (1 à 5).")
    period = SatisfactionPeriod.objects.select_for_update().get(pk=period.pk)
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
    except IntegrityError:
        raise ValidationError("Une réponse a déjà été enregistrée pour cette période.")
    audit(actor, "satisfaction.responded", response)
    return response
