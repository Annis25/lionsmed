"""Qui peut ouvrir quelle boîte institutionnelle — seule définition de cet accès.

La règle est celle du club : tant qu'une personne tient le rôle d'une fonction, elle a accès à
la boîte de cette fonction (capacité « mailbox.use » de apps.core.permissions, vérifiée avec la
boîte en objet). Aucune liste « telle personne ouvre telle boîte » n'existe : changer le rôle
d'un compte dans « Membres et mandats » suffit à retirer ou donner la lecture, l'envoi et les
avis, sans autre manipulation. Un mandat (« Notre bureau ») n'y joue aucun rôle.
"""
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.utils import timezone
from apps.core.permissions import can, effective_role
from apps.governance.models import RoleGrant
from .catalog import MAILBOXES, is_active


def holders(mailbox):
    """Titulaires actuels de la boîte (comptes), dans un ordre stable."""
    now = timezone.now()
    grants = (RoleGrant.objects.filter(role__in=mailbox.roles, starts_at__lte=now)
              .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))
              .filter(Q(revoked_at__isnull=True) | Q(revoked_at__gt=now)).select_related("user"))
    users = {grant.user_id: grant.user for grant in grants}
    # can() tranche : compte actif, profil de membre actif, rôle unique et sans ambiguïté.
    return [user for _, user in sorted(users.items(), key=lambda row: str(row[0])) if can(user, "mailbox.use", mailbox)]


def held_mailboxes(user):
    """Boîtes que le rôle du compte lui confie, reliées à Lionsmed ou non."""
    # Appelée à chaque page de l'espace privé (menu) : un seul contrôle complet, puis le
    # rôle déjà validé est rapproché du catalogue, plutôt que dix contrôles identiques.
    if not can(user, "mailbox.use"):
        return []
    role = effective_role(user)
    return [mailbox for mailbox in MAILBOXES if role in mailbox.roles]


def mailboxes_for(user):
    """Boîtes réellement utilisables par le compte : confiées par son rôle et reliées à Lionsmed."""
    return [mailbox for mailbox in held_mailboxes(user) if is_active(mailbox)]


def require_mailbox(user, mailbox):
    """À appeler dans chaque vue et chaque service : le menu n'est jamais une protection."""
    if mailbox is None or mailbox not in mailboxes_for(user):
        raise PermissionDenied
    return mailbox


def sender_for(user):
    """Boîte depuis laquelle le compte envoie ses communications, ou None : adresse générale du site.

    Décidée par le serveur à partir du rôle : rien de ce que transmet le navigateur ne la choisit."""
    return next(iter(mailboxes_for(user)), None)
