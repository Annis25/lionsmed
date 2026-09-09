from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from apps.core.models import AuditEvent
from .models import Role, RoleGrant


def require_operator(actor):
    # Procédure technique de bootstrap seulement, aucune délégation métier décidée.
    if not actor or not actor.is_active or not actor.is_staff or not actor.is_superuser:
        raise PermissionDenied("Opérateur technique requis.")


@transaction.atomic
def grant_role(*, actor, user, role, starts_at=None, ends_at=None):
    require_operator(actor)
    if role not in Role.values:
        raise ValidationError("Rôle inconnu.")
    get_user_model().objects.select_for_update().get(pk=user.pk)
    grant = RoleGrant(user=user, role=role, starts_at=starts_at or timezone.now(), ends_at=ends_at, granted_by=actor)
    grant.full_clean()
    grant.save()
    AuditEvent.objects.create(actor=actor, action="role.granted", object_type="RoleGrant", object_id=str(grant.pk))
    return grant


@transaction.atomic
def revoke_role(*, actor, grant):
    require_operator(actor)
    get_user_model().objects.select_for_update().get(pk=grant.user_id)
    current = RoleGrant.objects.select_for_update().get(pk=grant.pk)
    if current.revoked_at is None:
        current.revoked_at = timezone.now()
        current.save(update_fields=["revoked_at"])
        AuditEvent.objects.create(actor=actor, action="role.revoked", object_type="RoleGrant", object_id=str(current.pk))
    return current
