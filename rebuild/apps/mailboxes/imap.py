"""Connexion IMAP à une boîte — lecture seule.

Le dossier est ouvert en lecture seule et les messages lus avec BODY.PEEK : Lionsmed ne marque
rien comme lu sur le serveur et n'y supprime rien. Les erreurs sont ramenées à trois cas fixes
(SyncError.code) : le texte renvoyé par le serveur n'est jamais conservé ni journalisé.
"""
import imaplib
import re
import socket
import ssl
import time
from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from django.conf import settings

_SIZE = re.compile(rb"RFC822\.SIZE (\d+)")


class SyncError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


@dataclass
class Fetched:
    uid: int
    received_at: datetime
    size: int
    raw: bytes
    complete: bool  # False : message trop volumineux, seuls les en-têtes ont été lus


class ImapSession:
    def __init__(self, account):
        self.account = account
        self.connection = None

    def open(self):
        """Ouvre la boîte de réception et renvoie son UIDVALIDITY."""
        try:
            self.connection = imaplib.IMAP4_SSL(settings.MAILBOX_HOST, settings.MAILBOX_IMAP_PORT,
                ssl_context=ssl.create_default_context(), timeout=settings.MAILBOX_TIMEOUT)
        except ssl.SSLError:
            raise SyncError("tls_error") from None
        except (OSError, socket.timeout, imaplib.IMAP4.error):
            raise SyncError("unreachable") from None
        try:
            self.connection.login(self.account.username, self.account.password)
        except imaplib.IMAP4.abort:
            raise SyncError("unreachable") from None
        except (imaplib.IMAP4.error, UnicodeError):
            # « from None » : la réponse du serveur ne remonte dans aucune trace.
            raise SyncError("auth_failed") from None
        except (OSError, socket.timeout):
            raise SyncError("unreachable") from None
        status, _ = self._call(self.connection.select, "INBOX", readonly=True)
        if status != "OK":
            raise SyncError("protocol_error")
        _, data = self.connection.response("UIDVALIDITY")
        try:
            return int(data[0])
        except (TypeError, ValueError, IndexError):
            raise SyncError("protocol_error") from None

    def _call(self, command, *args, **kwargs):
        try:
            return command(*args, **kwargs)
        except (OSError, socket.timeout, imaplib.IMAP4.abort):
            raise SyncError("unreachable") from None
        except imaplib.IMAP4.error:
            raise SyncError("protocol_error") from None

    def uids_after(self, last_uid):
        status, data = self._call(self.connection.uid, "SEARCH", None, f"UID {last_uid + 1}:*")
        if status != "OK":
            raise SyncError("protocol_error")
        # « n:* » renvoie toujours le dernier message, même plus ancien que n : on refiltre.
        return sorted(uid for uid in (int(value) for value in (data[0] or b"").split()) if uid > last_uid)

    def fetch(self, uid, max_bytes):
        """Message complet, ou ses seuls en-têtes au-delà de max_bytes. None s'il a disparu."""
        status, data = self._call(self.connection.uid, "FETCH", str(uid), "(RFC822.SIZE INTERNALDATE)")
        line = data[0] if status == "OK" and data else None
        if not isinstance(line, bytes):
            return None
        size = int(match.group(1)) if (match := _SIZE.search(line)) else 0
        moment = imaplib.Internaldate2tuple(line)
        received_at = datetime.fromtimestamp(time.mktime(moment), tz=dt_timezone.utc) if moment else datetime.now(tz=dt_timezone.utc)
        complete = size <= max_bytes
        status, data = self._call(self.connection.uid, "FETCH", str(uid), "(BODY.PEEK[])" if complete else "(BODY.PEEK[HEADER])")
        raw = next((part[1] for part in (data or []) if isinstance(part, tuple) and len(part) > 1), None) if status == "OK" else None
        if not isinstance(raw, bytes):
            return None
        return Fetched(uid=uid, received_at=received_at, size=size, raw=raw, complete=complete)

    def close(self):
        if self.connection is None:
            return
        for command in (self.connection.close, self.connection.logout):
            try:
                command()
            except Exception:
                pass
        self.connection = None
