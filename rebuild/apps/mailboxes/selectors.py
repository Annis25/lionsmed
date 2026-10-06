"""Lectures de la Messagerie. Aucune ne contacte le serveur de messagerie : les pages
affichent la copie locale et l'état de la dernière synchronisation."""
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.db.models import Count
from django.urls import reverse
from django.utils import timezone
from apps.communications.models import OutboxMessage
from apps.communications.selectors import delivery_state, tracking_for
from . import catalog
from .access import mailboxes_for
from .models import InboundEmail, MailboxState, OutgoingEmail
from .services import OUTBOX_KIND


def mailbox_tabs(mailboxes, current):
    """Boîtes du compte, avec leur nombre de messages non lus (une requête)."""
    unread = dict(InboundEmail.objects.filter(mailbox__in=[mailbox.key for mailbox in mailboxes], read_at__isnull=True)
                  .values_list("mailbox").annotate(total=Count("id")))
    return [{"mailbox": mailbox, "unread": unread.get(mailbox.key, 0), "current": mailbox.key == current.key}
            for mailbox in mailboxes]


def sync_status(mailbox):
    """État de la synchronisation, en termes lisibles : jamais le code ni l'erreur du serveur."""
    state = MailboxState.objects.filter(mailbox=mailbox.key).first()
    return {"last_success_at": state.last_success_at if state else None,
            "failing": bool(state and state.last_error),
            "waiting": state is None or (state.last_success_at is None and not state.last_error)}


def when_label(moment, now=None):
    local = timezone.localtime(moment)
    today = timezone.localdate(now)
    if local.date() == today:
        return f"Aujourd’hui {local:%H:%M}"
    if local.date() == today - timedelta(days=1):
        return f"Hier {local:%H:%M}"
    return f"{local:%d/%m/%Y}"


def inbox_rows(emails):
    return [{"email": email, "sender": email.sender_name or email.sender_address or "Expéditeur inconnu",
             "when": when_label(email.received_at)} for email in emails]


def sent_rows(outgoings):
    outgoings = list(outgoings)
    tracking = tracking_for(OUTBOX_KIND, [outgoing.pk for outgoing in outgoings])
    return [{"outgoing": outgoing, "tracking": tracking[outgoing.pk], "when": when_label(outgoing.created_at),
             "to": ", ".join(outgoing.recipients)} for outgoing in outgoings]


def outgoing_recipients(outgoing):
    """Un état par destinataire, dans l'ordre du message (À, puis copie)."""
    items = {item.recipient.lower(): item for item in OutboxMessage.objects.filter(kind=OUTBOX_KIND, object_id=outgoing.pk)}
    rows = []
    for role, addresses in (("", outgoing.recipients), ("Copie", outgoing.copies)):
        for address in addresses:
            item = items.get(address.lower())
            if item is not None:
                rows.append({"email": address, "role": role, **delivery_state(item)})
    return rows


def readers(email):
    """Personnes ayant ouvert le message, dans l'ordre — utile dans une boîte partagée."""
    from apps.core.models import AuditEvent
    events = (AuditEvent.objects.filter(action="mailbox.message_opened", object_type="InboundEmail", object_id=str(email.pk))
              .order_by("created_at").values_list("actor_id", "created_at"))
    users = get_user_model().objects.in_bulk([actor_id for actor_id, _ in events])
    return [{"name": users[actor_id].get_full_name() or users[actor_id].email, "at": at}
            for actor_id, at in events if actor_id in users]


def message_url_for(actor, email_id):
    """Lien d'une notification vers son message, seulement si le compte y a toujours accès."""
    email = InboundEmail.objects.filter(pk=email_id).only("mailbox").first()
    mailbox = catalog.get(email.mailbox) if email else None
    if mailbox is None or mailbox not in mailboxes_for(actor):
        return None
    return reverse("mailboxes:message", args=[mailbox.key, email.pk])
