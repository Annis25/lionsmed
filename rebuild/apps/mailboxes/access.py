"""Qui peut ouvrir quelle boîte institutionnelle — seule définition de cet accès.

La source de vérité est le mandat (apps.governance.Mandate) : validé par le club, en cours à la
date du jour, et portant une fonction rattachée à la boîte (apps.mailboxes.catalog). Aucune liste
« telle personne ouvre telle boîte » n'existe : terminer un mandat ou en valider un nouveau suffit
à retirer ou donner l'accès, la lecture, l'envoi et les notifications, sans autre manipulation.

Ce n'est pas une capacité de apps.core.permissions.CAPABILITIES : ces capacités dépendent du rôle
applicatif, alors qu'un 1er et un 2e Vice-Président, par exemple, peuvent porter des rôles
différents. Le rôle ne sert ici qu'à vérifier que le compte a toujours accès à l'espace privé.
"""
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from apps.core.permissions import can
from apps.governance.functions import function_key
from apps.governance.models import Mandate
from apps.members.models import MemberProfile
from .catalog import MAILBOXES, is_active


def _current_mandates(today=None):
    today = today or timezone.localdate()
    return Mandate.objects.filter(
        validated_at__isnull=False, starts_on__lte=today, ends_on__gt=today,
        profile__status=MemberProfile.Status.ACTIVE, profile__user__is_active=True)


def holders(mailbox, *, today=None):
    """Titulaires actuels de la boîte (comptes), dans un ordre stable."""
    users = {}
    for mandate in _current_mandates(today).select_related("profile__user"):
        if function_key(mandate.function) in mailbox.functions:
            users[mandate.profile.user_id] = mandate.profile.user
    return [user for _, user in sorted(users.items(), key=lambda row: str(row[0]))
            if can(user, "account.access_private_area")]


def held_mailboxes(user, *, today=None):
    """Boîtes que les mandats en cours du compte lui confient, reliées à Lionsmed ou non."""
    if not can(user, "account.access_private_area"):
        return []
    labels = _current_mandates(today).filter(profile__user_id=user.pk).values_list("function", flat=True)
    keys = {function_key(label) for label in labels}
    return [mailbox for mailbox in MAILBOXES if mailbox.functions & keys]


def mailboxes_for(user, *, today=None):
    """Boîtes réellement utilisables par le compte : confiées par un mandat et reliées à Lionsmed."""
    return [mailbox for mailbox in held_mailboxes(user, today=today) if is_active(mailbox)]


def require_mailbox(user, mailbox):
    """À appeler dans chaque vue et chaque service : le menu n'est jamais une protection."""
    if mailbox is None or mailbox not in mailboxes_for(user):
        raise PermissionDenied
    return mailbox


def sender_for(user, requested=""):
    """Boîte depuis laquelle le compte envoie, décidée par le serveur.

    Sans boîte : chaîne vide (adresse générale du site). Une seule boîte : celle-ci. Plusieurs :
    `requested` doit en désigner une. Toute autre valeur — boîte d'une autre fonction, clé
    fabriquée — est un refus, jamais un repli silencieux sur une autre identité."""
    from django.core.exceptions import ValidationError
    allowed = {mailbox.key: mailbox for mailbox in mailboxes_for(user)}
    if requested:
        if requested not in allowed:
            raise PermissionDenied
        return allowed[requested]
    if len(allowed) > 1:
        raise ValidationError("Choisissez l’adresse depuis laquelle envoyer ce message.")
    return next(iter(allowed.values()), None)
