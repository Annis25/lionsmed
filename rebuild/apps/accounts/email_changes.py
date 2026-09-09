"""Préparation uniquement : aucune adresse n'est écrite sans preuve de confirmation."""
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from apps.core.permissions import can
from .models import normalize_email

def validate_new_email(value):
    normalized = normalize_email(value)
    validate_email(normalized)
    if len(normalized) > 254 or get_user_model().objects.filter(email=normalized).exists():
        raise ValidationError("Cette adresse ne peut pas être utilisée.")
    return normalized

def request_email_change(*, actor, user, new_email):
    if not can(actor, "account.change_email", user): raise PermissionDenied
    validate_new_email(new_email)
    # Ne pas créer une fausse preuve « confirmed=True » fournie par l'appelant.
    # À brancher à une demande expirante, preuve nouvelle adresse, réauth et audit atomique.
    raise ValidationError("Confirmation sécurisée sur la nouvelle adresse non disponible. Aucune modification effectuée.")
