"""Lectures de la gouvernance — projection publique « Notre bureau » et liste de gestion des mandats.

La seule source est le mandat (`Mandate`) : fonction réellement exercée, rattachée à
une Année Lions, validée par le club et autorisée à la publication. Le rôle applicatif
(`RoleGrant`, `apps.core.permissions`) n'intervient jamais ici : une fonction du bureau
n'est pas une permission (un « 1er Vice-Président » et un « 2e Vice-Président » peuvent
partager le même rôle VICE_PRESIDENT, un « Protocole » n'a aucun rôle dédié).

L'ordre et la reconnaissance des fonctions viennent du catalogue apps.governance.functions
(source unique, partagée avec le formulaire de saisie) : un libellé hors catalogue n'est ni
écarté ni deviné, il s'affiche après les fonctions ordonnées, tel qu'il a été saisi.
"""
from datetime import timedelta
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from apps.core.permissions import can
from apps.members.models import MemberProfile
from .functions import function_key, function_rank, normalize_function
from .models import ClubState, LionsYear, Mandate


def reference_year(today=None):
    """Année Lions de référence : l'année active déclarée par le club, sinon celle qui
    contient la date du jour. Aucune année devinée au-delà."""
    state = ClubState.objects.select_related("active_year").first()
    if state and state.active_year:
        return state.active_year
    today = today or timezone.localdate()
    return LionsYear.objects.filter(starts_on__lte=today, ends_on__gt=today).first()


def _public_mandates():
    """Seuls les mandats validés, autorisés à la publication, d'un compte actif et non
    suspendu peuvent apparaître publiquement."""
    return (Mandate.objects.filter(validated_at__isnull=False, public_authorized=True, profile__user__is_active=True)
            .exclude(profile__status=MemberProfile.Status.SUSPENDED)
            .select_related("profile__user", "lions_year"))


def _person(mandate, *, function, note=""):
    profile = mandate.profile
    user = profile.user
    # Photo et lien uniquement si le membre a lui-même activé son profil public :
    # c'est l'autorisation explicite de diffusion de son portrait (route publique
    # /membres/<slug>/photo/ qui revérifie ces mêmes conditions à chaque requête).
    public = bool(profile.public_profile_enabled and profile.public_slug)
    first, last = user.first_name.strip(), user.last_name.strip()
    return {
        "name": user.get_full_name().strip(),
        "initials": ((first[:1] + last[:1]) or user.get_full_name().strip()[:1]).upper(),
        "function": function,
        "note": note,
        "profile_url": f"/membres/{profile.public_slug}/" if public else "",
        "photo_url": f"/membres/{profile.public_slug}/photo/" if public and profile.photo_key else "",
        "_sort": (function_rank(function), normalize_function(function), last.lower(), first.lower()),
    }


def _derived_past_president(year):
    """Past President déduit : le président de l'Année Lions immédiatement précédente,
    seulement si ce mandat est validé et autorisé à la publication. En cas de doute
    (deux présidents terminant l'année à la même date), rien n'est affiché."""
    previous = LionsYear.objects.filter(starts_on__lt=year.starts_on).order_by("-starts_on").first()
    if not previous:
        return None
    presidents = [m for m in _public_mandates().filter(lions_year=previous) if function_key(m.function) == "PRESIDENT"]
    if not presidents:
        return None
    last_end = max(m.ends_on for m in presidents)
    finishing = [m for m in presidents if m.ends_on == last_end]
    if len(finishing) != 1 or not finishing[0].profile.user.get_full_name().strip():
        return None
    return _person(finishing[0], function="Past President", note=f"{finishing[0].function} {previous.label}")


def public_bureau(today=None):
    """Bureau public de l'Année Lions de référence, dans l'ordre institutionnel.

    Retourne {"year": LionsYear|None, "members": [dict]} ; chaque membre ne porte que des
    données publiques (nom, fonction, photo et lien de profil public autorisés)."""
    today = today or timezone.localdate()
    year = reference_year(today)
    qs = _public_mandates()
    if year:
        # Mandats de l'année de référence qui ne sont pas déjà terminés (un remplacement
        # en cours d'année retire l'ancien titulaire sans attendre la fin de l'année).
        qs = qs.filter(lions_year=year, ends_on__gt=today)
    else:
        qs = qs.filter(starts_on__lte=today, ends_on__gt=today)
    members = [_person(m, function=m.function) for m in qs if m.profile.user.get_full_name().strip()]
    # Le Past President déduit complète un bureau existant ; seul, il laisserait croire
    # que le bureau de l'année se résume à lui.
    if year and members and not any(function_key(m["function"]) == "PAST_PRESIDENT" for m in members):
        derived = _derived_past_president(year)
        if derived:
            members.append(derived)
    members.sort(key=lambda member: member["_sort"])
    for member in members:
        del member["_sort"]
    return {"year": year, "members": members}


def year_mandates(actor, year, today=None):
    """Mandats d'une Année Lions pour l'espace de gestion (tous états, ordre du bureau).
    Projection explicite : aucune coordonnée, aucun objet User transmis au gabarit."""
    if not can(actor, "members.view_management"):
        raise PermissionDenied
    today = today or timezone.localdate()
    rows = []
    for mandate in Mandate.objects.filter(lions_year=year).select_related("profile__user"):
        user = mandate.profile.user
        if mandate.ends_on <= today:
            period = "ENDED"
        elif mandate.starts_on > today:
            period = "UPCOMING"
        else:
            period = "CURRENT"
        rows.append({
            "id": mandate.pk, "function": mandate.function, "member_id": user.pk,
            "member": user.get_full_name().strip() or "Membre sans nom",
            "starts_on": mandate.starts_on, "last_day": mandate.ends_on - timedelta(days=1), "period": period,
            "validated": bool(mandate.validated_at), "public_authorized": mandate.public_authorized,
            "can_end": mandate.starts_on < today < mandate.ends_on,
            "recognised": function_key(mandate.function) is not None,
            "_sort": (function_rank(mandate.function), normalize_function(mandate.function), mandate.starts_on,
                      user.last_name.lower(), user.first_name.lower()),
        })
    rows.sort(key=lambda row: row["_sort"])
    for row in rows:
        del row["_sort"]
    return rows


def mandate_candidates(include=None):
    """Membres pouvant recevoir un mandat : membres actifs de l'annuaire (ni compte technique
    SUPER_ADMIN, ni invité, ni suspendu). `include` garde le titulaire d'un mandat existant
    même s'il ne remplit plus ces conditions, pour pouvoir corriger son historique."""
    from django.db.models import OuterRef, Q, Subquery
    from apps.core.permissions import DIRECTORY_ROLES
    from .models import RoleGrant
    now = timezone.now()
    grants = RoleGrant.objects.filter(user_id=OuterRef("user_id"), starts_at__lte=now).filter(
        Q(ends_at__isnull=True) | Q(ends_at__gt=now)).filter(Q(revoked_at__isnull=True) | Q(revoked_at__gt=now))
    qs = MemberProfile.objects.select_related("user").annotate(current_role=Subquery(grants.values("role")[:1]))
    eligible = Q(status=MemberProfile.Status.ACTIVE, user__is_active=True, current_role__in=DIRECTORY_ROLES)
    if include:
        eligible |= Q(pk=include)
    return qs.filter(eligible).order_by("user__last_name", "user__first_name", "user_id")
