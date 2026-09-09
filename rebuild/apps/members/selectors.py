from django.core.exceptions import PermissionDenied
from django.db.models import Q, OuterRef, Subquery
from django.core.paginator import Paginator
from django.http import Http404
from django.urls import reverse
from django.utils import timezone
from apps.core.permissions import can, effective_role, MEMBERS, DIRECTORY_ROLES
from apps.governance.models import Role, RoleGrant
from .models import MemberProfile, AssociationExperience

def require(actor, capability, obj=None):
    if not can(actor, capability, obj): raise PermissionDenied

def own_profile(actor):
    require(actor, "profile.view_own")
    return MemberProfile.objects.select_related("user").get(user_id=actor.pk)

def scoped_profiles(actor, *, management=False):
    require(actor, "members.view_management" if management else "directory.view")
    now = timezone.now()
    grants = RoleGrant.objects.filter(user_id=OuterRef("user_id"), starts_at__lte=now).filter(
        Q(ends_at__isnull=True) | Q(ends_at__gt=now)).filter(Q(revoked_at__isnull=True) | Q(revoked_at__gt=now))
    qs = MemberProfile.objects.select_related("user").annotate(current_role=Subquery(grants.values("role")[:1]))
    if not management:
        qs = qs.filter(status="ACTIVE", user__is_active=True, current_role__in=DIRECTORY_ROLES)
    return qs.order_by("user__last_name", "user__first_name", "user_id")

def member_profile(actor, user_id, *, management=False):
    try: profile = scoped_profiles(actor, management=management).get(user_id=user_id)
    except MemberProfile.DoesNotExist: raise Http404
    if not management and not can(actor, "member.view", profile): raise Http404
    return profile

def profile_data(actor, profile, *, own=False, management=False):
    require(actor, "profile.view_own" if own else "members.view_management" if management else "member.view", profile)
    # Projection explicite : aucun objet User/profil d'autrui dans le contexte HTML.
    role = effective_role(profile.user)
    dto = {"id":profile.user_id, "name":profile.user.get_full_name() or "Membre", "role":Role(role).label if role else "Aucun rôle actif"}
    visible = own or management or (profile.status == "ACTIVE" and profile.user.is_active and role in DIRECTORY_ROLES)
    for field in ["profession", "bio"]:
        if visible: dto[field] = getattr(profile, field)
    if visible: dto.update(email=profile.user.email, phone=profile.phone)
    if profile.photo_key and visible:
        dto["photo_url"] = reverse("members:photo", args=[profile.user_id])
    if visible:
        dto["experiences"] = list(profile.experiences.values("id","network","club","function","district","start_year","end_year","description","achievements"))
    if visible:
        mandates = profile.mandates.select_related("lions_year")
        if not own and not management: mandates = mandates.filter(validated_at__isnull=False)
        dto["mandates"] = [{"function":m.function,"year":m.lions_year.label,"starts_on":m.starts_on,"ends_on":m.ends_on,"validated":bool(m.validated_at)} for m in mandates]
    if own or management:
        dto.update(status=profile.get_status_display(), account_active=profile.user.is_active)
    if own: dto["directory_visible"] = profile.directory_visible
    return dto

def directory_page(actor, params, *, management=False):
    qs = scoped_profiles(actor, management=management)
    query = params.get("q", "").strip()[:100]; role = params.get("role", "")
    if query:
        qs = qs.filter(Q(user__first_name__icontains=query) | Q(user__last_name__icontains=query)
            | Q(profession__icontains=query))
    if role in Role.values: qs = qs.filter(current_role=role)
    status = params.get("status", "") if management else ""
    if status in MemberProfile.Status.values: qs = qs.filter(status=status)
    page = Paginator(qs, 12).get_page(params.get("page"))
    page.object_list = [profile_data(actor,p,management=management) for p in page.object_list]
    return page

def own_experience(actor, experience_id):
    require(actor, "experience.manage_own")
    try: item = AssociationExperience.objects.select_related("profile").get(pk=experience_id, profile__user_id=actor.pk)
    except AssociationExperience.DoesNotExist: raise Http404
    require(actor, "experience.manage_own", item)
    return item
