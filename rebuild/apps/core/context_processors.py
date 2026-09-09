from django.conf import settings
from django.urls import reverse
from .permissions import can


def shell(request):
    navigation=[("Accueil",reverse("core:home")),("Notre Club",reverse("editorial:club")),("Nos Actions",reverse("actions:list")),("Nous rejoindre",reverse("editorial:join")),("Contact",reverse("communications:contact"))]
    if not request.path.startswith("/espace/"):
        from apps.editorial.selectors import institution
        from apps.agenda.models import Event
        return {"public_navigation":navigation,"institution":institution(),
            "has_public_events":Event.objects.public().exists(),
            "canonical_url":settings.SITE_ORIGIN+(reverse("accounts:reset") if request.path.startswith("/reinitialiser/") else request.path)}
    from apps.members.models import MemberProfile
    photo_key = MemberProfile.objects.filter(user_id=request.user.pk).values_list("photo_key", flat=True).first()

    def entries(rows):
        return [{"label": label, "url": reverse(route)} for label, route, capability in rows if can(request.user, capability)]

    private_navigation = entries([
        ("Tableau de bord", "core:dashboard", "account.access_private_area"),
        ("Mon profil", "members:profile", "profile.view_own"),
        ("Mon parcours", "members:experiences", "experience.manage_own"),
        ("Mot de passe", "accounts:password_change", "account.change_own_password"),
        ("Annuaire", "members:directory", "directory.view"),
        ("Calendrier", "agenda_private:calendar", "event.register"),
    ])
    if can(request.user, "satisfaction.manage"):
        satisfaction_children = entries([("Répondre", "satisfaction:respond", "satisfaction.respond")])
        satisfaction_children += entries([("Gestion", "satisfaction:manage_list", "satisfaction.manage")])
        private_navigation.append({"label": "Satisfaction", "children": satisfaction_children})
    else:
        private_navigation += entries([("Satisfaction", "satisfaction:respond", "satisfaction.respond")])
    if can(request.user, "document.manage"):
        document_children = entries([("Mes documents", "documents:list", "document.view")])
        document_children += entries([("Gestion", "documents:manage_list", "document.manage")])
        private_navigation.append({"label": "Documents", "children": document_children})
    else:
        private_navigation += entries([("Documents", "documents:list", "document.view")])
    # « Votes » se déplie pour un responsable (créer/gérer regroupés) ; reste un lien
    # simple pour un électeur sans capacité de gestion.
    if can(request.user, "vote.manage"):
        children = entries([("Voter", "voting:member_list", "vote.cast")])
        children += entries([
            ("Créer un vote", "voting:manage_create", "vote.manage"),
            ("Gestion des votes", "voting:manage_list", "vote.manage"),
        ])
        # Désigner un responsable reste un acte du bureau, même pour un responsable
        # déjà nommé nominativement (pas de délégation en cascade).
        children += entries([("Responsables de vote", "voting:manage_responsibles", "management.access")])
        private_navigation.append({"label": "Votes", "children": children})
    else:
        private_navigation += entries([("Votes", "voting:member_list", "vote.cast")])
    if can(request.user, "dues.manage") or can(request.user, "dues.view_management"):
        dues_children = entries([("Mes cotisations", "dues:own", "dues.view_own")])
        dues_children += entries([("Gestion", "dues:manage_list", "dues.view_management")])
        private_navigation.append({"label": "Cotisations", "children": dues_children})
    else:
        private_navigation += entries([("Cotisations", "dues:own", "dues.view_own")])
    private_navigation += entries([
        ("Notifications", "notifications:list", "notification.view_own"),
        ("Contenu public", "editorial_management:dashboard", "public_content.access_management"),
    ])
    if can(request.user, "application.view"):
        private_navigation.append({"label": "Candidatures", "url": reverse("communications:inbox", args=["application"])})
    if can(request.user, "contact.view"):
        private_navigation.append({"label": "Messages de contact", "url": reverse("communications:inbox", args=["contact"])})
    private_navigation += entries([
        ("Membres et mandats", "governance:members", "members.view_management"),
        ("Authentification forte", "accounts:mfa_setup", "mfa.manage_own"),
        ("Années Lions", "governance:years", "year.view"),
    ])
    # Pilotage a rejoint le tableau de bord (voir apps.core.views.dashboard) ; la page
    # dédiée est supprimée. Statistiques et Présences restent accessibles par URL directe
    # mais sont volontairement masquées du menu pour l'instant.
    return {
        "header_photo_url": reverse("members:photo", args=[request.user.pk]) if photo_key else None,
        "can_directory": can(request.user, "directory.view"),
        "can_management": can(request.user, "management.access"),
        "private_navigation": private_navigation,
        "can_private": can(request.user, "account.access_private_area"),
        "can_change_password": can(request.user, "account.change_own_password"),
        "public_navigation": navigation,
        # Jamais un token reset ni une query string dans le canonical.
        "canonical_url": settings.SITE_ORIGIN + (reverse("accounts:reset") if request.path.startswith("/reinitialiser/") else request.path),
    }
