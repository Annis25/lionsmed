"""Envoi au nom d'une boîte institutionnelle : un seul point d'entrée pour les dix comptes.

Chaque boîte est un vrai compte du serveur de messagerie : on s'y authentifie avec ses propres
identifiants et l'expéditeur est toujours l'adresse de la boîte authentifiée. Aucun repli sur
une autre identité : une boîte non reliée à Lionsmed lève SenderUnavailable.
"""
from django.conf import settings
from django.core.mail import get_connection
from . import catalog


class SenderUnavailable(Exception):
    pass


def connection_for(key):
    """(expéditeur, connexion SMTP) de la boîte `key`."""
    mailbox = catalog.get(key)
    credentials = catalog.account(mailbox) if mailbox else None
    if credentials is None:
        raise SenderUnavailable
    connection = get_connection(settings.MAILBOX_EMAIL_BACKEND, host=settings.MAILBOX_HOST,
        port=settings.MAILBOX_SMTP_PORT, username=credentials.username, password=credentials.password,
        use_ssl=True, use_tls=False, timeout=settings.MAILBOX_TIMEOUT)
    return mailbox.sender, connection
