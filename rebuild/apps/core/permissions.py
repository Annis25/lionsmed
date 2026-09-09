from functools import wraps
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.utils import timezone
from apps.governance.models import Role, RoleGrant
from apps.members.models import MemberProfile, AssociationExperience

# Seulement les deux capacités des vues privées effectivement livrées.
PERSONAL = frozenset(Role.values)
MEMBERS = PERSONAL - {Role.INVITE}
MANAGERS = frozenset({Role.SUPER_ADMIN, Role.PRESIDENT, Role.SECRETAIRE})
# Palier « bureau » des documents : BUREAU/PRESIDENT/SECRETAIRE/SUPER_ADMIN. DIRECTEUR en est
# exclu tant que ses capacités avancées ne sont pas confirmées humainement.
BUREAU_LEVEL = frozenset({Role.SUPER_ADMIN, Role.PRESIDENT, Role.SECRETAIRE, Role.BUREAU})
CAPABILITIES = {
    "account.access_private_area": PERSONAL,
    "account.change_own_password": PERSONAL,
    "public_content.access_management": MANAGERS,
    "action.create": MANAGERS, "action.edit": MANAGERS, "action.publish": MANAGERS,
    "event.create": MANAGERS, "event.edit": MANAGERS, "event.publish": MANAGERS,
    "editorial.manage": MANAGERS, "image.manage": MANAGERS,
    "application.view": MANAGERS, "application.manage": MANAGERS,
    "contact.view": MANAGERS, "contact.manage": MANAGERS,
    "profile.view_own": PERSONAL, "profile.edit_own": PERSONAL,
    "experience.manage_own": PERSONAL,
    "directory.view": MEMBERS, "member.view": MEMBERS,
    "members.view_management": MANAGERS, "management.access": MANAGERS,
    "year.view": MANAGERS,
    # Calendrier, présences, documents, cotisations et notifications (phase fonctionnement quotidien).
    "event.register": MEMBERS, "attendance.record": MANAGERS,
    "document.view": PERSONAL, "document.manage": MANAGERS,
    "notification.view_own": PERSONAL, "notification.send": MANAGERS,
    "dues.view_own": PERSONAL, "dues.manage": MANAGERS,
    "statistics.view": MANAGERS,
    # Votes et satisfaction (Phase B). INVITE jamais électeur ; DIRECTEUR/BUREAU sans gestion.
    "vote.manage": MANAGERS, "vote.cast": MEMBERS, "vote.view_results": MEMBERS,
    "satisfaction.respond": MEMBERS, "satisfaction.manage": MANAGERS, "satisfaction.view_results": MANAGERS,
    # MFA (Phase C) : mêmes comptes que les capacités de gestion sensibles.
    "mfa.manage_own": MANAGERS,
    # Services présents, mais aucune délégation de mutation validée.
    "mandate.manage": frozenset(), "account.change_email": frozenset(),
}


def effective_role(user, *, at=None):
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return None
    now = at or timezone.now()
    roles = list(RoleGrant.objects.filter(user_id=user.pk, starts_at__lte=now)
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))
        .filter(Q(revoked_at__isnull=True) | Q(revoked_at__gt=now))
        .values_list("role", flat=True)[:2])
    # État ambigu : refus, jamais choisir le rôle le plus puissant.
    return roles[0] if len(roles) == 1 and roles[0] in Role.values else None


def can(user, capability, obj=None):
    allowed = CAPABILITIES.get(capability)
    if not allowed:
        return False
    role = effective_role(user)
    if role not in allowed:
        return False
    status = MemberProfile.objects.filter(user_id=user.pk).values_list("status", flat=True).first()
    if status is None or status == MemberProfile.Status.SUSPENDED:
        return False
    if status == MemberProfile.Status.GUEST and role != Role.INVITE:
        return False
    if capability in {"directory.view", "member.view"} and status != MemberProfile.Status.ACTIVE:
        return False
    if obj is not None:
        public_types = {"action": "service_actions.action", "event": "agenda.event",
            "application":"members.membershipapplication", "contact":"communications.contactrequest",
            "vote": "voting.vote", "satisfaction": "satisfaction.satisfactionperiod"}
        if capability == "dues.view_own":
            from apps.dues.models import DuesRecord
            return isinstance(obj, DuesRecord) and obj.profile.user_id == user.pk
        if capability == "notification.view_own":
            from apps.communications.models import Notification
            return isinstance(obj, Notification) and obj.recipient_id == user.pk
        prefix = capability.split(".")[0]
        if prefix in public_types:
            return getattr(getattr(obj, "_meta", None), "label_lower", None) == public_types[prefix]
        if capability.startswith("account."):
            return isinstance(obj, get_user_model()) and obj.pk == user.pk
        if capability in {"profile.view_own", "profile.edit_own", "experience.manage_own"}:
            owner_id = obj.user_id if isinstance(obj, MemberProfile) else (obj.profile.user_id if isinstance(obj, AssociationExperience) else None)
            return owner_id == user.pk
        if capability == "member.view":
            return (isinstance(obj, MemberProfile) and obj.directory_visible and obj.status == MemberProfile.Status.ACTIVE
                    and obj.user.is_active and effective_role(obj.user) in MEMBERS)
        if capability == "members.view_management":
            return isinstance(obj, MemberProfile)
        return False

    return True


def capability_required(capability):
    def decorate(view):
        @login_required
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not can(request.user, capability):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return decorate
