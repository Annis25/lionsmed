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
                ("Pilotage", "governance:dashboard", "management.access"),
                ("Membres et mandats", "governance:members", "members.view_management"),
                ("Années Lions", "governance:years", "year.view"),
            ] if can(request.user, capability)
        ],
        "can_private": can(request.user, "account.access_private_area"),
        "can_change_password": can(request.user, "account.change_own_password"),
        "public_navigation": navigation,
        # Jamais un token reset ni une query string dans le canonical.
        "canonical_url": settings.SITE_ORIGIN + (reverse("accounts:reset") if request.path.startswith("/reinitialiser/") else request.path),
    }
