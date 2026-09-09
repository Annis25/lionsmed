from django.conf import settings
from django.urls import reverse
from .permissions import can


def shell(request):
    return {
        "can_directory": can(request.user, "directory.view"),
        "can_management": can(request.user, "management.access"),
        "private_navigation": [
            {"label":label, "url":reverse(route)}
            for label, route, capability in [
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
        "public_navigation": [
            ("Accueil", reverse("core:home")), ("Notre Club", None),
            ("Nos Actions", None), ("Nous rejoindre", None), ("Contact", None),
        ],
        # Jamais un token reset ni une query string dans le canonical.
        "canonical_url": settings.SITE_ORIGIN + (reverse("accounts:reset") if request.path.startswith("/reinitialiser/") else request.path),
    }
