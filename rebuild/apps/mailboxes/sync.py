"""Synchronisation des boîtes : serveur de messagerie → copie locale.

Appelée par la commande planifiée `sync_mailboxes`, jamais pendant l'affichage d'une page.
Mêmes principes que l'outbox : bail court posé en base (deux exécutions qui se chevauchent
ne traitent pas la même boîte), aucune transaction ouverte pendant les échanges réseau,
reprise sans doublon (UID et empreinte uniques), échec propre boîte par boîte.
"""
import logging
from datetime import timedelta
from uuid import uuid4
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from apps.core.models import AuditEvent
from .catalog import MAILBOXES, account
from .imap import ImapSession, SyncError
from .models import InboundEmail, MailboxState
from .parsing import Parsed, parse
from .services import notify_holders

logger = logging.getLogger("lionsmed.mailboxes")
LEASE = timedelta(minutes=10)
UNREADABLE = "Ce message n’a pas pu être lu par Lionsmed. Consultez-le depuis votre logiciel de messagerie habituel."
TOO_LARGE = "Ce message est trop volumineux pour être affiché dans Lionsmed. Consultez-le depuis votre logiciel de messagerie habituel."


def _retry_delay(code, failures):
    # Un mot de passe refusé à chaque minute ferait bannir le serveur par l'hébergeur de
    # messagerie : on espace nettement plus qu'après une simple coupure réseau.
    if code == "auth_failed":
        return min(timedelta(minutes=15 * 2 ** (failures - 1)), timedelta(hours=6))
    return min(timedelta(minutes=2 ** failures), timedelta(minutes=30))


def _take(mailbox, now):
    """Pose le bail sur la boîte ; None si une autre exécution la traite ou si elle est en attente."""
    MailboxState.objects.get_or_create(mailbox=mailbox.key)
    with transaction.atomic():
        state = MailboxState.objects.select_for_update(skip_locked=True).filter(mailbox=mailbox.key).first()
        if state is None or (state.lease_until and state.lease_until > now):
            return None, "busy"
        if state.next_attempt_at and state.next_attempt_at > now:
            return None, "deferred"
        state.lease_token, state.lease_until, state.last_attempt_at = uuid4(), now + LEASE, now
        state.save(update_fields=["lease_token", "lease_until", "last_attempt_at"])
    return state, ""


def _store(mailbox, state, fetched, readable=True):
    """Enregistre un message et avance le curseur, en une transaction. True si une ligne est créée."""
    try:
        parsed = parse(fetched.raw) if readable else None
    except Exception:
        parsed = None
    partial = parsed is None or not fetched.complete
    if parsed is None:
        parsed = Parsed(fingerprint=f"uid:{state.uid_validity}:{fetched.uid}", subject="(message illisible)", body_text=UNREADABLE)
    elif not fetched.complete:
        parsed.body_text, parsed.body_html, parsed.preview, parsed.attachments = TOO_LARGE, "", "", []
    created = False
    with transaction.atomic():
        duplicate = InboundEmail.objects.filter(mailbox=mailbox.key).filter(
            fingerprint=parsed.fingerprint).exists() or InboundEmail.objects.filter(
            mailbox=mailbox.key, uid_validity=state.uid_validity, uid=fetched.uid).exists()
        if not parsed.own_notice and not duplicate:
            email = InboundEmail.objects.create(
                mailbox=mailbox.key, uid_validity=state.uid_validity, uid=fetched.uid, fingerprint=parsed.fingerprint,
                message_id=parsed.message_id, references=parsed.references, sender_name=parsed.sender_name,
                sender_address=parsed.sender_address, reply_to=parsed.reply_to, recipients=parsed.recipients,
                copies=parsed.copies, subject=parsed.subject, received_at=fetched.received_at, preview=parsed.preview,
                body_text=parsed.body_text, body_html=parsed.body_html, attachments=parsed.attachments,
                size=fetched.size, partial=partial, automatic=parsed.automatic)
            created = True
            if fetched.uid > state.silent_until_uid:
                notify_holders(mailbox, email)
        MailboxState.objects.filter(mailbox=mailbox.key, lease_token=state.lease_token).update(last_uid=fetched.uid)
    state.last_uid = fetched.uid
    return created


def _pull(mailbox, state, session):
    uid_validity = session.open()
    if state.uid_validity != uid_validity:
        # Premier passage (ou boîte reconstruite par le serveur) : on reprend les messages les
        # plus récents, sans notifier personne pour du courrier déjà ancien.
        existing = session.uids_after(0)
        recent = existing[-settings.MAILBOX_INITIAL_IMPORT:]
        state.uid_validity = uid_validity
        state.last_uid = recent[0] - 1 if recent else 0
        state.silent_until_uid = existing[-1] if existing else 0
        MailboxState.objects.filter(mailbox=mailbox.key, lease_token=state.lease_token).update(
            uid_validity=state.uid_validity, last_uid=state.last_uid, silent_until_uid=state.silent_until_uid)
    imported = 0
    for uid in session.uids_after(state.last_uid)[:settings.MAILBOX_SYNC_BATCH]:
        fetched = session.fetch(uid, settings.MAILBOX_MAX_MESSAGE_BYTES)
        if fetched is None:
            # Supprimé entre la recherche et la lecture : on passe au suivant.
            MailboxState.objects.filter(mailbox=mailbox.key, lease_token=state.lease_token).update(last_uid=uid)
            state.last_uid = uid
            continue
        try:
            try:
                imported += int(_store(mailbox, state, fetched))
            except IntegrityError:
                raise
            except Exception:
                # Un message qui ne se laisse pas enregistrer ne doit pas bloquer les suivants :
                # il est repris sous forme de simple signalement.
                imported += int(_store(mailbox, state, fetched, readable=False))
        except Exception:
            # Même message enregistré entre-temps par une autre exécution, ou signalement
            # lui-même impossible : on avance, la boîte d'origine reste intacte sur le serveur.
            MailboxState.objects.filter(mailbox=mailbox.key, lease_token=state.lease_token).update(last_uid=uid)
            state.last_uid = uid
    return imported


def sync_mailbox(mailbox, *, session_factory=ImapSession, now=None):
    """Synchronise une boîte. Ne lève jamais : renvoie {"status": code, "imported": n}."""
    credentials = account(mailbox)
    if credentials is None:
        return {"status": "inactive", "imported": 0}
    now = now or timezone.now()
    state, reason = _take(mailbox, now)
    if state is None:
        return {"status": reason, "imported": 0}
    session, code, imported = None, "", 0
    try:
        session = session_factory(credentials)
        imported = _pull(mailbox, state, session)
    except SyncError as error:
        code = error.code
    except Exception:
        code = "unexpected"
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass
    with transaction.atomic():
        current = MailboxState.objects.select_for_update().get(mailbox=mailbox.key)
        if current.lease_token == state.lease_token:
            current.lease_token, current.lease_until = None, None
            if code:
                first = not current.last_error
                current.failures = min(current.failures + 1, 100)
                current.last_error = code
                current.next_attempt_at = timezone.now() + _retry_delay(code, current.failures)
                if first:
                    # Une ligne d'audit par panne, pas une par minute de panne.
                    AuditEvent.objects.create(actor=None, action="mailbox.sync_failed", object_type="Mailbox",
                                              object_id=mailbox.key, result=code[:16])
            else:
                current.failures, current.last_error, current.next_attempt_at = 0, "", None
                current.last_success_at = timezone.now()
            current.save()
    if code:
        # Clé de boîte et code fixe uniquement : ni réponse du serveur, ni identifiant.
        logger.warning("mailbox_sync_failed mailbox=%s code=%s", mailbox.key, code)
    return {"status": code or "ok", "imported": imported}


def sync_all(*, session_factory=ImapSession):
    """Une boîte après l'autre, jamais en parallèle : une seule connexion ouverte à la fois."""
    return {mailbox.key: sync_mailbox(mailbox, session_factory=session_factory) for mailbox in MAILBOXES}
