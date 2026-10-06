"""Contenu des deux types de messages d'outbox liés aux boîtes institutionnelles.

L'envoi lui-même reste celui de l'outbox existante (apps.communications.outbox) : mêmes
tentatives, mêmes états, même sens du mot « Envoyé ».
"""
from django.template.loader import render_to_string
from apps.communications.emailing import absolute, base_context, safe_subject
from . import catalog
from .access import holders
from .models import InboundEmail, OutgoingEmail
from .parsing import NOTICE_DOMAIN, NOTICE_HEADER, NOTICE_SUBJECT


def message_parts(item):
    """Message écrit depuis une boîte : tel que saisi, sans habillage ni salutation ajoutée."""
    outgoing = OutgoingEmail.objects.select_related("in_reply_to").filter(pk=item.object_id).first()
    mailbox = catalog.get(outgoing.mailbox) if outgoing else None
    if mailbox is None:
        return None
    # Même Message-ID pour tous les destinataires : c'est un seul et même message.
    headers = {"To": ", ".join(outgoing.recipients), "Message-ID": f"<{outgoing.pk}@{mailbox.address.split('@')[1]}>"}
    if outgoing.copies:
        headers["Cc"] = ", ".join(outgoing.copies)
    original = outgoing.in_reply_to
    if original is not None and original.message_id:
        headers["In-Reply-To"] = original.message_id
        headers["References"] = " ".join((original.references.split()[-20:] + [original.message_id]))[:900]
    context = {"body": outgoing.body}
    return (outgoing.subject, render_to_string("emails/mailbox_message.txt", context),
            render_to_string("emails/mailbox_message.html", context), headers)


def notice_parts(item, notification):
    """Avis de nouveau message, pour l'adresse personnelle d'un titulaire.

    Revérifié à l'envoi : si la personne ne tient plus la boîte (mandat terminé entre-temps),
    l'avis ne part pas. Les en-têtes le désignent comme message automatique de Lionsmed, pour
    qu'aucun répondeur n'y réponde et qu'il ne soit jamais repris comme courrier institutionnel."""
    email = InboundEmail.objects.filter(pk=notification.target_id).first()
    mailbox = catalog.get(email.mailbox) if email else None
    user = notification.recipient
    if mailbox is None or user not in holders(mailbox):
        return None
    context = base_context(user, mailbox=mailbox, email=email,
        sender=f"{email.sender_name} <{email.sender_address}>" if email.sender_name else email.sender_address,
        url=absolute(f"/espace/messagerie/{mailbox.key}/message/{email.pk}/"))
    subject = safe_subject(f"{NOTICE_SUBJECT} {mailbox.address} — {email.subject or '(sans objet)'}")
    headers = {"Message-ID": f"<{item.pk}@{NOTICE_DOMAIN}>", NOTICE_HEADER: "mailbox",
               "Auto-Submitted": "auto-generated", "X-Auto-Response-Suppress": "All"}
    return (subject, render_to_string("emails/mailbox_notice.txt", context),
            render_to_string("emails/mailbox_notice.html", context), headers)
