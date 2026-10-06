"""Les dix boîtes e-mail institutionnelles du club — catalogue fixe.

Une boîte appartient à une fonction du club, jamais à une personne : ce fichier ne contient
aucun nom ni aucun compte. Les personnes autorisées sont, à chaque requête, celles qui tiennent
le rôle de la fonction (apps.mailboxes.access). Le fournisseur limite le club à dix boîtes : on
n'en crée pas ici, on décrit celles qui existent.

Les mots de passe ne figurent ni ici ni en base : ils viennent de la configuration du serveur
(settings.MAILBOX_PASSWORDS, alimenté par le fichier .env). Une boîte sans mot de passe
configuré est simplement inactive dans Lionsmed.
"""
from dataclasses import dataclass
from django.conf import settings
from apps.governance.models import Role

CLUB_NAME = "Lions Club Sfax-Méditerranée"


@dataclass(frozen=True)
class Mailbox:
    key: str            # identifiant stable : URL, base de données, configuration
    address: str
    label: str
    roles: frozenset    # rôles (apps.governance.models.Role) dont les titulaires utilisent la boîte

    @property
    def sender(self):
        """Identité d'expéditeur : toujours la boîte, jamais l'adresse personnelle du titulaire."""
        return f"{CLUB_NAME} — {self.label} <{self.address}>"


@dataclass(frozen=True)
class Account:
    username: str
    password: str

    def __repr__(self):
        # Jamais de mot de passe dans une trace, un journal ou une page d'erreur.
        return f"<Compte de messagerie {self.username}>"

    __str__ = __repr__


MAILBOXES = (
    Mailbox("president", "president@lionsmed.tn", "Présidence", frozenset({Role.PRESIDENT})),
    # Boîte commune à tous les comptes qui tiennent le rôle Vice-président (1er et 2e).
    Mailbox("vice-president", "vice.president@lionsmed.tn", "Vice-présidence", frozenset({Role.VICE_PRESIDENT})),
    Mailbox("secretariat", "secretariat@lionsmed.tn", "Secrétariat", frozenset({Role.SECRETAIRE})),
    Mailbox("tresorier", "tresorier@lionsmed.tn", "Trésorerie", frozenset({Role.TRESORIER})),
    Mailbox("president-fondateur", "president.fondateur@lionsmed.tn", "Président fondateur",
            frozenset({Role.PRESIDENT_FONDATEUR})),
    Mailbox("directeur", "directeur@lionsmed.tn", "Direction", frozenset({Role.DIRECTEUR})),
    Mailbox("gmt", "gmt@lionsmed.tn", "Effectif (GMT)", frozenset({Role.GMT})),
    Mailbox("gst", "gst@lionsmed.tn", "Service (GST)", frozenset({Role.GST})),
    Mailbox("lcif", "lcif@lionsmed.tn", "LCIF", frozenset({Role.LCIF})),
    Mailbox("marketing-communication", "marketing.communication@lionsmed.tn", "Marketing et communication",
            frozenset({Role.MARKETING_COMMUNICATION})),
)
_BY_KEY = {mailbox.key: mailbox for mailbox in MAILBOXES}
ADDRESSES = frozenset(mailbox.address for mailbox in MAILBOXES)


def get(key):
    return _BY_KEY.get(key)


def account(mailbox):
    """Identifiants de connexion de la boîte, ou None si elle n'est pas reliée à Lionsmed."""
    password = settings.MAILBOX_PASSWORDS.get(mailbox.key)
    if not password:
        return None
    return Account(settings.MAILBOX_USERNAMES.get(mailbox.key) or mailbox.address, password)


def is_active(mailbox):
    return bool(settings.MAILBOX_PASSWORDS.get(mailbox.key))
