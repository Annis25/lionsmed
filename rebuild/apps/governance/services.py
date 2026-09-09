from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.contrib.auth import get_user_model
from apps.core.models import AuditEvent
from apps.core.permissions import can, effective_role
from apps.accounts.models import normalize_email
from apps.members.models import MemberProfile
from datetime import date
from .models import Role, RoleGrant, LionsYear, ClubState


def require(actor, capability, obj=None):
    if not can(actor, capability, obj):
        raise PermissionDenied


def audit(actor, action, obj):
    AuditEvent.objects.create(actor=actor, action=action, object_type=obj._meta.object_name, object_id=str(obj.pk))


def _guard_not_super_admin(user):
    # Le Super administrateur ne se crée, ne se modifie ni ne se rétrograde depuis cette
    # page métier : uniquement via la procédure technique (createsuperuser / CLI grant_role).
    if effective_role(user) == Role.SUPER_ADMIN:
        raise PermissionDenied("Le compte Super administrateur ne se modifie pas depuis cette page.")


@transaction.atomic
def create_member(*, actor, first_name, last_name, email, role):
    require(actor, "members.manage")
    if role not in Role.values or role == Role.SUPER_ADMIN:
        raise ValidationError("Rôle invalide pour une création depuis cette page.")
    email = normalize_email(email)
    User = get_user_model()
    if User.objects.filter(email=email).exists():
        raise ValidationError("Cette adresse e-mail est déjà associée à un compte.")
    user = User.objects.create_user(email, None, first_name=first_name[:150], last_name=last_name[:150])
    MemberProfile.objects.create(user=user, status=MemberProfile.Status.GUEST if role == Role.INVITE else MemberProfile.Status.ACTIVE)
    grant = RoleGrant(user=user, role=role, starts_at=timezone.now(), granted_by=actor)
    grant.full_clean()
    grant.save()
    from apps.communications.models import OutboxMessage
    # Invitation individuelle via l'outbox : aucun mot de passe n'est généré ni connu du gestionnaire.
    OutboxMessage.objects.create(event_key=f"activation:{user.pk}", kind="ACTIVATION", recipient=user.email, object_id=user.pk)
    audit(actor, "member.created", user)
    audit(actor, "role.granted", grant)
    return user


@transaction.atomic
def resend_member_invitation(*, actor, target_user):
    require(actor, "members.manage")
    target_user = get_user_model().objects.select_for_update().get(pk=target_user.pk)
    _guard_not_super_admin(target_user)
    if target_user.has_usable_password():
        raise ValidationError("L’invitation ne peut être renvoyée qu’à un compte non encore activé.")
    from apps.communications.models import OutboxMessage
    slot = int(timezone.now().timestamp() // 300)
    OutboxMessage.objects.get_or_create(event_key=f"activation:{target_user.pk}:{slot}", defaults={
        "kind": "ACTIVATION", "recipient": target_user.email, "object_id": target_user.pk,
    })
    audit(actor, "member.invitation_resent", target_user)
    return target_user


@transaction.atomic
def set_role(*, actor, target_user, role):
    require(actor, "members.manage")
    if role not in Role.values or role == Role.SUPER_ADMIN:
        raise ValidationError("Rôle invalide pour une attribution depuis cette page.")
    target_user = get_user_model().objects.select_for_update().get(pk=target_user.pk)
    _guard_not_super_admin(target_user)
    now = timezone.now()
    active = RoleGrant.objects.select_for_update().filter(user=target_user, starts_at__lte=now).filter(
        Q(ends_at__isnull=True) | Q(ends_at__gt=now)).filter(Q(revoked_at__isnull=True) | Q(revoked_at__gt=now))
    for grant in active:
        grant.revoked_at = now
        grant.save(update_fields=["revoked_at"])
        audit(actor, "role.revoked", grant)
    new_grant = RoleGrant(user=target_user, role=role, starts_at=now, granted_by=actor)
    new_grant.full_clean()
    new_grant.save()
    audit(actor, "role.granted", new_grant)
    return new_grant


@transaction.atomic
def set_member_status(*, actor, profile, status):
    require(actor, "members.manage")
    if status not in MemberProfile.Status.values:
        raise ValidationError("Statut invalide.")
    profile = MemberProfile.objects.select_for_update().get(pk=profile.pk)
    _guard_not_super_admin(profile.user)
    profile.status = status
    profile.full_clean()
    profile.save(update_fields=["status", "updated_at"])
    audit(actor, "member.status_changed", profile)
    return profile


@transaction.atomic
def set_member_email(*, actor, target_user, email):
    require(actor, "members.manage")
    email = normalize_email(email)
    User = get_user_model()
    target_user = User.objects.select_for_update().get(pk=target_user.pk)
    _guard_not_super_admin(target_user)
    if User.objects.exclude(pk=target_user.pk).filter(email=email).exists():
        raise ValidationError("Cette adresse e-mail est déjà associée à un autre compte.")
    target_user.email = email
    target_user.full_clean()
    target_user.save(update_fields=["email", "updated_at"])
    audit(actor, "member.email_changed", target_user)
    return target_user


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


@transaction.atomic
def create_lions_year(*, actor, start_year):
    """Calendrier confirmé par le club : juillet (année N) → juillet (année N+1)."""
    require(actor, "year.manage")
    starts_on = date(start_year, 7, 1)
    ends_on = date(start_year + 1, 7, 1)
    year = LionsYear(starts_on=starts_on, ends_on=ends_on)
    try:
        year.full_clean()
    except Exception as error:
        raise ValidationError("Année invalide ou chevauchant une période déjà enregistrée.") from error
    year.save()
    audit(actor, "year.created", year)
    set_active_year(actor=actor, lions_year=year)
    return year


@transaction.atomic
def set_active_year(*, actor, lions_year):
    require(actor, "year.manage")
    lions_year = LionsYear.objects.select_for_update().get(pk=lions_year.pk)
    state, _ = ClubState.objects.select_for_update().get_or_create(pk=1)
    state.active_year = lions_year
    state.full_clean()
    state.save()
    audit(actor, "year.activated", lions_year)
    return state


@transaction.atomic
def set_year_archived(*, actor, lions_year, archived):
    require(actor, "year.manage")
    lions_year = LionsYear.objects.select_for_update().get(pk=lions_year.pk)
    lions_year.archived_at = timezone.now() if archived else None
    lions_year.full_clean()
    lions_year.save(update_fields=["archived_at"])
    audit(actor, "year.archived" if archived else "year.unarchived", lions_year)
    return lions_year
