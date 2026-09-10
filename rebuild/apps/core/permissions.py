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
DIRECTORY_ROLES = MEMBERS - {Role.SUPER_ADMIN}
MANAGERS = frozenset({Role.SUPER_ADMIN, Role.PRESIDENT, Role.PRESIDENT_FONDATEUR, Role.SECRETAIRE})
CONTACT_INBOX_ROLES = frozenset({Role.PRESIDENT, Role.SECRETAIRE})
APPLICATION_INBOX_ROLES = frozenset({Role.PRESIDENT, Role.GMT})
# Palier « bureau » des documents : BUREAU/PRESIDENT/SECRETAIRE/SUPER_ADMIN. DIRECTEUR en est
# exclu tant que ses capacités avancées ne sont pas confirmées humainement.
BUREAU_LEVEL = frozenset({Role.SUPER_ADMIN, Role.PRESIDENT, Role.SECRETAIRE, Role.BUREAU})
# Communication générale : périmètre explicitement validé, indépendant de la simple
# visibilité d'un lien de navigation. Les responsables techniques (GST/GMT/GLT/LCIF)
# et DIRECTEUR n'y accèdent pas par défaut.
BROADCAST_EMAIL_ROLES = frozenset({Role.SUPER_ADMIN, Role.PRESIDENT, Role.VICE_PRESIDENT,
    Role.SECRETAIRE, Role.TRESORIER, Role.BUREAU})
# Cotisations (recette V2) : seul le Trésorier (+ Super Admin) modifie ; le reste du
# bureau (PRESIDENT/SECRETAIRE/BUREAU) consulte sans modifier — décision explicite du
# club, qui retire ce droit de modification à PRESIDENT/SECRETAIRE.
DUES_MANAGERS = frozenset({Role.SUPER_ADMIN, Role.TRESORIER})
DUES_VIEWERS = BUREAU_LEVEL | {Role.TRESORIER}
CAPABILITIES = {
    "account.access_private_area": PERSONAL,
    "account.change_own_password": PERSONAL,
    "public_content.access_management": MANAGERS,
    "action.create": MANAGERS, "action.edit": MANAGERS, "action.publish": MANAGERS,
    "event.create": MANAGERS, "event.edit": MANAGERS, "event.publish": MANAGERS,
    "editorial.manage": MANAGERS, "image.manage": MANAGERS,
    "application.view": APPLICATION_INBOX_ROLES, "application.manage": APPLICATION_INBOX_ROLES,
    "contact.view": CONTACT_INBOX_ROLES, "contact.manage": CONTACT_INBOX_ROLES,
    "profile.view_own": PERSONAL, "profile.edit_own": PERSONAL,
    "experience.manage_own": PERSONAL,
    "directory.view": MEMBERS, "member.view": MEMBERS,
    "members.view_management": MANAGERS, "members.manage": MANAGERS, "management.access": MANAGERS,
    "year.view": MANAGERS, "year.manage": MANAGERS,
    # Calendrier, présences, documents, cotisations et notifications (phase fonctionnement quotidien).
    "event.register": MEMBERS, "attendance.record": MANAGERS,
    "document.view": PERSONAL, "document.manage": MANAGERS,
    "notification.view_own": PERSONAL, "notification.send": MANAGERS,
    "communication.send_member_broadcast": BROADCAST_EMAIL_ROLES,
    "communication.view_member_broadcast": BROADCAST_EMAIL_ROLES,
    "dues.view_own": PERSONAL, "dues.manage": DUES_MANAGERS, "dues.view_management": DUES_VIEWERS,
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


def _is_designated_vote_manager(user):
    return MemberProfile.objects.filter(user_id=user.pk, is_vote_manager=True).exists()


def can(user, capability, obj=None):
    allowed = CAPABILITIES.get(capability)
    if not allowed:
        return False
    role = effective_role(user)
    # « vote.manage » peut aussi être accordé individuellement (désignation nominative,
    # indépendante du rôle) — voir apps.voting.services.set_vote_manager. Seul un
    # PRESIDENT/SECRETAIRE/SUPER_ADMIN peut faire cette désignation (management.access).
    if role not in allowed and not (capability == "vote.manage" and role is not None and _is_designated_vote_manager(user)):
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
            return (isinstance(obj, MemberProfile) and obj.status == MemberProfile.Status.ACTIVE
                    and obj.user.is_active and effective_role(obj.user) in DIRECTORY_ROLES)
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
