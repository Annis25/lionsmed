from django.conf import settings
from django.urls import reverse
from .permissions import can


def shell(request):
    navigation=[("Accueil",reverse("core:home")),("Notre Club",reverse("editorial:club")),("Nos Actions",reverse("actions:list")),("Nous rejoindre",reverse("editorial:join")),("Contact",reverse("communications:contact"))]
    if not request.path.startswith("/espace/"):
        from apps.editorial.selectors import institution
        return {"public_navigation":navigation,"institution":institution(),"canonical_url":settings.SITE_ORIGIN+(reverse("accounts:reset") if request.path.startswith("/reinitialiser/") else request.path)}
    return {
        "can_directory": can(request.user, "directory.view"),
        "can_management": can(request.user, "management.access"),
        "private_navigation": [
            {"label":label, "url":reverse(route)}
            for label, route, capability in [
                ("Contenu public", "editorial_management:dashboard", "public_content.access_management"),
                ("Mon profil", "members:profile", "profile.view_own"),
                ("Mon parcours", "members:experiences", "experience.manage_own"),
                ("Annuaire", "members:directory", "directory.view"),
                ("Calendrier", "agenda_private:calendar", "event.register"),
                ("Votes", "voting:member_list", "vote.cast"),
                ("Satisfaction", "satisfaction:respond", "satisfaction.respond"),
                ("Documents", "documents:list", "document.view"),
                ("Notifications", "notifications:list", "notification.view_own"),
                ("Cotisations", "dues:own", "dues.view_own"),
                ("Pilotage", "governance:dashboard", "management.access"),
                ("Membres et mandats", "governance:members", "members.view_management"),
                ("Années Lions", "governance:years", "year.view"),
                ("Présences", "agenda_private:attendance_events", "attendance.record"),
                ("Gestion des documents", "documents:manage_list", "document.manage"),
                ("Gestion des cotisations", "dues:manage_list", "dues.manage"),
                ("Créer un vote", "voting:manage_create", "vote.manage"),
                ("Gestion des votes", "voting:manage_list", "vote.manage"),
                ("Satisfaction agrégée", "satisfaction:manage_list", "satisfaction.manage"),
                ("Statistiques", "governance:statistics", "statistics.view"),
                ("Authentification forte", "accounts:mfa_setup", "mfa.manage_own"),
            ] if can(request.user, capability)
        ],
        "can_private": can(request.user, "account.access_private_area"),
        "can_change_password": can(request.user, "account.change_own_password"),
        "public_navigation": navigation,
        # Jamais un token reset ni une query string dans le canonical.
        "canonical_url": settings.SITE_ORIGIN + (reverse("accounts:reset") if request.path.startswith("/reinitialiser/") else request.path),
    }
