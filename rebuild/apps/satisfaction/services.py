from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction, IntegrityError
from django.db.models import Max
from django.utils import timezone
from apps.core.permissions import can
from apps.core.models import AuditEvent
from .models import SatisfactionPeriod, SatisfactionResponse, SatisfactionAxis, SatisfactionAxisScore

RULE_VERSION = "phase-b-v2"
MAX_AXES = 30
MAX_AXIS_LABEL_LENGTH = 180


def require(actor, capability, obj=None):
    if not can(actor, capability, obj):
        raise PermissionDenied


def audit(actor, action, obj):
    # Jamais de note ni de commentaire : uniquement type/identifiant d'objet.
    AuditEvent.objects.create(actor=actor, action=action, object_type=obj._meta.object_name, object_id=str(obj.pk))


def _validate_window(opens_at, closes_at):
    if not opens_at or not closes_at:
        raise ValidationError("Indiquez la date et l'heure de lancement et de fermeture.")
    if closes_at <= opens_at:
        raise ValidationError("La fermeture doit être postérieure au lancement.")


def _month_of(opens_at):
    return timezone.localtime(opens_at).date().replace(day=1)


def _clean_axis_labels(labels):
    cleaned = [str(label).strip() for label in (labels or []) if str(label).strip()]
    if len(cleaned) > MAX_AXES:
        raise ValidationError(f"{MAX_AXES} axes maximum.")
    if any(len(label) > MAX_AXIS_LABEL_LENGTH for label in cleaned):
        raise ValidationError(f"{MAX_AXIS_LABEL_LENGTH} caractères maximum par axe.")
    if len({label.casefold() for label in cleaned}) != len(cleaned):
        raise ValidationError("Chaque axe doit avoir un nom différent.")
    return cleaned


@transaction.atomic
def create_period(*, actor, opens_at, closes_at, threshold, title="", description="", axes=None):
    require(actor, "satisfaction.manage")
    _validate_window(opens_at, closes_at)
    # Plusieurs consultations peuvent désormais partager le même mois (demande
    # explicite) : `month` n'est plus qu'un libellé/tri dérivé de opens_at, jamais une
    # clé d'unicité — voir la période ouverte simultanément côté respond().
    labels = _clean_axis_labels(axes)
    period = SatisfactionPeriod(month=_month_of(opens_at), title=title, description=description, rule_version=RULE_VERSION,
        opens_at=opens_at, closes_at=closes_at, threshold=threshold, created_by=actor)
    period.full_clean()
    period.save()
    audit(actor, "satisfaction.period_created", period)
    for order, label in enumerate(labels, start=1):
        axis = SatisfactionAxis(period=period, label=label, order=order)
        axis.full_clean()
        axis.save()
        audit(actor, "satisfaction.axis_added", axis)
    return period


@transaction.atomic
def update_period(*, actor, period, opens_at, closes_at, threshold, title="", description=""):
    require(actor, "satisfaction.manage")
    period = SatisfactionPeriod.objects.select_for_update().get(pk=period.pk)
    has_responses = period.responses.exists()
    if has_responses and (period.opens_at != opens_at or period.closes_at != closes_at or period.threshold != threshold):
        raise ValidationError("Des réponses existent déjà : dates et seuil de confidentialité sont figés.")
    if not has_responses:
        _validate_window(opens_at, closes_at)
        period.month = _month_of(opens_at)
        period.opens_at = opens_at
        period.closes_at = closes_at
        period.threshold = threshold
    period.title = title
    period.description = description
    period.rule_version = RULE_VERSION
    period.full_clean()
    period.save()
    audit(actor, "satisfaction.period_updated", period)
    return period


def _ensure_axes_editable(period):
    # Politique volontairement stricte (identique à l'ancien comportement testé) : dès la
    # première réponse, tout changement structurel des axes (ajout/suppression/ordre/
    # libellé) est bloqué, jamais silencieusement — un axe modifié après coup fausserait
    # la lecture des moyennes déjà accumulées par les répondants précédents.
    if period.responses.exists():
        raise ValidationError("Des réponses existent déjà pour cette consultation : les axes sont figés pour préserver la cohérence des résultats.")


@transaction.atomic
def add_axis(*, actor, period, label):
    require(actor, "satisfaction.manage")
    period = SatisfactionPeriod.objects.select_for_update().get(pk=period.pk)
    _ensure_axes_editable(period)
    label = label.strip()
    if not label:
        raise ValidationError("Le nom de l'axe est obligatoire.")
    if len(label) > MAX_AXIS_LABEL_LENGTH:
        raise ValidationError(f"{MAX_AXIS_LABEL_LENGTH} caractères maximum.")
    if period.axes.count() >= MAX_AXES:
        raise ValidationError(f"{MAX_AXES} axes maximum.")
    if period.axes.filter(label__iexact=label).exists():
        raise ValidationError("Cet axe existe déjà.")
    next_order = (period.axes.aggregate(top=Max("order"))["top"] or 0) + 1
    axis = SatisfactionAxis(period=period, label=label, order=next_order)
    axis.full_clean()
    axis.save()
    audit(actor, "satisfaction.axis_added", axis)
    return axis


@transaction.atomic
def update_axis(*, actor, axis, label):
    require(actor, "satisfaction.manage")
    period = SatisfactionPeriod.objects.select_for_update().get(pk=axis.period_id)
    _ensure_axes_editable(period)
    label = label.strip()
    if not label:
        raise ValidationError("Le nom de l'axe est obligatoire.")
    if len(label) > MAX_AXIS_LABEL_LENGTH:
        raise ValidationError(f"{MAX_AXIS_LABEL_LENGTH} caractères maximum.")
    if period.axes.exclude(pk=axis.pk).filter(label__iexact=label).exists():
        raise ValidationError("Cet axe existe déjà.")
    axis.label = label
    axis.full_clean()
    axis.save(update_fields=["label"])
    audit(actor, "satisfaction.axis_updated", axis)
    return axis


@transaction.atomic
def delete_axis(*, actor, axis):
    require(actor, "satisfaction.manage")
    period = SatisfactionPeriod.objects.select_for_update().get(pk=axis.period_id)
    _ensure_axes_editable(period)
    audit(actor, "satisfaction.axis_deleted", axis)  # avant delete() : delete() vide axis.pk
    axis.delete()


@transaction.atomic
def move_axis(*, actor, axis, direction):
    require(actor, "satisfaction.manage")
    period = SatisfactionPeriod.objects.select_for_update().get(pk=axis.period_id)
    _ensure_axes_editable(period)
    axes = list(period.axes.order_by("order", "pk"))
    index = next(i for i, item in enumerate(axes) if item.pk == axis.pk)
    swap_index = index - 1 if direction == "up" else index + 1
    if 0 <= swap_index < len(axes):
        other = axes[swap_index]
        axis.order, other.order = other.order, axis.order
        SatisfactionAxis.objects.bulk_update([axis, other], ["order"])
        audit(actor, "satisfaction.axis_reordered", axis)
    return axis


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
    response = SatisfactionResponse(period=period, profile=profile, score=score, comment=comment[:500])
    try:
        response.full_clean()
        response.save()
        SatisfactionAxisScore.objects.bulk_create([SatisfactionAxisScore(response=response, axis=axis, score=axis_scores[axis.pk]) for axis in axes])
    except IntegrityError:
        raise ValidationError("Une réponse a déjà été enregistrée pour cette période.")
    audit(actor, "satisfaction.responded", response)
    return response
