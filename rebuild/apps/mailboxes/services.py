import hashlib
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone
from apps.communications.emailing import safe_subject
from apps.communications.models import OutboxMessage
from apps.communications.services import RETRYABLE_ERROR_CODES, notify
from apps.core.models import AuditEvent
from apps.core.throttling import consume
from .access import holders, require_mailbox
from .models import InboundEmail, OutgoingEmail

OUTBOX_KIND = "MAILBOX_MESSAGE"
MAX_RECIPIENTS = 10
SENDS_PER_HOUR = 40
NOTICES_PER_HOUR = 30


def audit(actor, action, obj):
    AuditEvent.objects.create(actor=actor, action=action, object_type=obj._meta.object_name, object_id=str(obj.pk))


def notify_holders(mailbox, email):
    """Prévient les titulaires actuels de la boîte : toujours dans Lionsmed, et par e-mail à
    leur adresse personnelle sauf si cela risque d'entretenir une boucle.

    L'e-mail est un simple avis (expéditeur, objet, lien) : le contenu reste dans Lionsmed.
    Pas d'e-mail pour une réponse automatique, un avis de non-remise ou un message qui renvoie
    à un avis Lionsmed (voir parsing._automatic), ni au-delà d'un plafond horaire par boîte :
    même si un filtre échappait aux contrôles, une boucle s'éteint d'elle-même."""
    by_email = not email.automatic and consume("mailbox-notice", mailbox.key, limit=NOTICES_PER_HOUR, seconds=3600)
    sender = email.sender_name or email.sender_address or "expéditeur inconnu"
    for user in holders(mailbox):
        notify(recipient=user, category="MESSAGE", title=f"Nouveau message reçu sur {mailbox.address}",
               excerpt=f"De : {sender} — Objet : {email.subject or '(sans objet)'}",
               event_key=f"mailbox:{email.pk}:{user.pk}", target_kind="mailbox", target_id=email.pk,
               email=by_email, outbox_kind="MAILBOX_NOTICE")


@transaction.atomic
def open_message(*, actor, mailbox, email):
    """Ouverture d'un message : le marque lu pour la boîte et garde la trace de qui l'a ouvert."""
    require_mailbox(actor, mailbox)
    if email.mailbox != mailbox.key:
        raise PermissionDenied
    if email.read_at is None:
        InboundEmail.objects.filter(pk=email.pk, read_at__isnull=True).update(read_at=timezone.now(), read_by=actor)
        email.refresh_from_db(fields=["read_at", "read_by"])
    # Une ligne par personne et par message : dans une boîte partagée, on sait qui a lu quoi.
    if not AuditEvent.objects.filter(action="mailbox.message_opened", object_type="InboundEmail",
                                     object_id=str(email.pk), actor=actor).exists():
        audit(actor, "mailbox.message_opened", email)
    return email


@transaction.atomic
def mark_unread(*, actor, mailbox, email):
    require_mailbox(actor, mailbox)
    if email.mailbox != mailbox.key:
        raise PermissionDenied
    if InboundEmail.objects.filter(pk=email.pk, read_at__isnull=False).update(read_at=None, read_by=None):
        audit(actor, "mailbox.message_marked_unread", email)


def _addresses(values):
    seen, result = set(), []
    for value in values:
        address = (value or "").strip()
        if not address or address.lower() in seen:
            continue
        # validate_email refuse espaces, retours à la ligne et caractères de contrôle :
        # aucune adresse ne peut injecter un en-tête supplémentaire.
        validate_email(address)
        seen.add(address.lower())
        result.append(address)
    return result


def _event_key(outgoing_id, address):
    return f"mailbox:{outgoing_id}:{hashlib.sha1(address.lower().encode()).hexdigest()}"


@transaction.atomic
def send_message(*, actor, mailbox, to, subject, body, idempotency_key, cc=(), in_reply_to=None):
    """Met en file un message écrit au nom de la boîte : une ligne d'outbox par destinataire.

    L'expéditeur n'est pas un paramètre : c'est la boîte, dont l'accès est revérifié ici."""
    require_mailbox(actor, mailbox)
    # Verrou sur l'auteur : une double soumission retrouve le message créé par la première.
    actor = get_user_model().objects.select_for_update().get(pk=actor.pk)
    existing = OutgoingEmail.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        if existing.mailbox != mailbox.key or existing.author_id != actor.pk:
            raise PermissionDenied
        return existing, False
    if in_reply_to is not None and in_reply_to.mailbox != mailbox.key:
        raise PermissionDenied
    recipients = _addresses(to)
    copies = [address for address in _addresses(cc) if address.lower() not in {value.lower() for value in recipients}]
    if not recipients:
        raise ValidationError("Indiquez au moins un destinataire.")
    if len(recipients) + len(copies) > MAX_RECIPIENTS:
        raise ValidationError(f"{MAX_RECIPIENTS} destinataires maximum par message.")
    subject = safe_subject(subject)
    body = (body or "").replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not subject or not body:
        raise ValidationError("L’objet et le message sont obligatoires.")
    if len(body) > 20000:
        raise ValidationError("Le message est trop long (20 000 caractères maximum).")
    if not consume("mailbox-send", mailbox.key, limit=SENDS_PER_HOUR, seconds=3600):
        raise ValidationError("Trop de messages ont été envoyés depuis cette boîte en une heure. Réessayez un peu plus tard.")
    outgoing = OutgoingEmail.objects.create(mailbox=mailbox.key, author=actor, idempotency_key=idempotency_key,
        recipients=recipients, copies=copies, subject=subject, body=body, in_reply_to=in_reply_to)
    OutboxMessage.objects.bulk_create([OutboxMessage(
        event_key=_event_key(outgoing.pk, address), kind=OUTBOX_KIND, recipient=address,
        object_id=outgoing.pk, sender_mailbox=mailbox.key) for address in recipients + copies])
    audit(actor, "mailbox.reply_sent" if in_reply_to else "mailbox.message_sent", outgoing)
    return outgoing, True


@transaction.atomic
def retry_failed(*, actor, mailbox, outgoing):
    """Remet en file les échecs de livraison d'un message, sur les mêmes lignes d'outbox."""
    require_mailbox(actor, mailbox)
    outgoing = OutgoingEmail.objects.select_for_update().get(pk=outgoing.pk)
    if outgoing.mailbox != mailbox.key:
        raise PermissionDenied
    retried = OutboxMessage.objects.filter(kind=OUTBOX_KIND, object_id=outgoing.pk, state="FAILED",
        error_code__in=RETRYABLE_ERROR_CODES).update(state="PENDING", attempts=0, available_at=timezone.now(),
        error_code="", lease_token=None, lease_until=None, sent_at=None)
    if retried:
        audit(actor, "mailbox.message_retried", outgoing)
    return retried
