from django.db import transaction
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from apps.core.permissions import can
from apps.core.models import AuditEvent
from .functions import validate_function
from .models import Mandate, LionsYear


def _require_manager(actor):
    get_user_model().objects.select_for_update().get(pk=actor.pk)
    if not can(actor, "mandate.manage"): raise PermissionDenied


def _audit(actor, action, mandate_id):
    AuditEvent.objects.create(actor=actor, action=action, object_type="Mandate", object_id=str(mandate_id))


@transaction.atomic
def save_mandate(*, actor, data, mandate=None):
    """Crée ou corrige un mandat. `validated` (booléen) date et signe la validation au nom de
    l'acteur ; `public_authorized` autorise l'affichage dans « Notre bureau ». Un mandat
    n'accorde ni ne retire jamais de rôle applicatif."""
    _require_manager(actor)
    allowed = {"profile", "function", "lions_year", "starts_on", "ends_on", "public_authorized", "validated"}
    if set(data) - allowed: raise ValidationError("Champs de mandat non autorisés.")
    data = dict(data)
    validated = data.pop("validated", None)
    if "function" in data: data["function"] = validate_function(data["function"])
    if mandate: mandate = Mandate.objects.select_for_update().get(pk=mandate.pk)
    else: mandate = Mandate()
    for key, value in data.items(): setattr(mandate, key, value)
    if validated is True and not mandate.validated_at:
        mandate.validated_at, mandate.validated_by = timezone.now(), actor
    elif validated is False:
        mandate.validated_at, mandate.validated_by = None, None
    LionsYear.objects.select_for_update().get(pk=mandate.lions_year_id)
    mandate.full_clean(); mandate.save()
    _audit(actor, "mandate.saved", mandate.pk)
    return mandate


@transaction.atomic
def end_mandate(*, actor, mandate, today=None):
    """Termine un mandat en cours : il cesse à la date du jour (fin exclusive) et reste dans
    l'historique. Un mandat qui n'a pas encore commencé ou déjà terminé se corrige ou se supprime."""
    _require_manager(actor)
    mandate = Mandate.objects.select_for_update().get(pk=mandate.pk)
    today = today or timezone.localdate()
    if not mandate.starts_on < today < mandate.ends_on:
        raise ValidationError("Seul un mandat commencé avant aujourd’hui et encore en cours peut être terminé.")
    mandate.ends_on = today
    mandate.full_clean(); mandate.save(update_fields=["ends_on", "updated_at"])
    _audit(actor, "mandate.ended", mandate.pk)
    return mandate


@transaction.atomic
def delete_mandate(*, actor, mandate):
    """Supprime une saisie erronée (mauvaise personne, mauvaise année). Pour une fin de
    fonction réelle, end_mandate conserve l'historique."""
    _require_manager(actor)
    mandate = Mandate.objects.select_for_update().get(pk=mandate.pk)
    mandate_id = mandate.pk
    mandate.delete()
    _audit(actor, "mandate.deleted", mandate_id)
