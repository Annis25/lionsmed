"""Copie locale des boîtes institutionnelles.

`mailbox` est partout la clé du catalogue (apps.mailboxes.catalog), jamais une personne : les
messages appartiennent à la fonction et restent en place quand le titulaire change.
"""
import uuid
from django.conf import settings
from django.db import models


class MailboxState(models.Model):
    """Avancement de la synchronisation d'une boîte (une ligne par boîte, créée au premier passage)."""
    mailbox = models.CharField(max_length=40, primary_key=True)
    uid_validity = models.PositiveBigIntegerField(null=True, blank=True)
    last_uid = models.PositiveBigIntegerField(default=0)
    # Messages déjà présents à la première synchronisation : importés sans notification.
    silent_until_uid = models.PositiveBigIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    failures = models.PositiveSmallIntegerField(default=0)
    # Code fixe (auth_failed, unreachable…), jamais le message brut du serveur.
    last_error = models.CharField(max_length=24, blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    lease_token = models.UUIDField(null=True, blank=True)


class InboundEmail(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mailbox = models.CharField(max_length=40)
    uid_validity = models.PositiveBigIntegerField()
    uid = models.PositiveBigIntegerField()
    # Empreinte du Message-ID (ou du message entier s'il n'en a pas) : même message, une seule ligne.
    fingerprint = models.CharField(max_length=64)
    message_id = models.CharField(max_length=255, blank=True)
    references = models.TextField(blank=True)
    sender_name = models.CharField(max_length=200, blank=True)
    sender_address = models.CharField(max_length=254, blank=True)
    reply_to = models.CharField(max_length=254, blank=True)
    recipients = models.JSONField(default=list, blank=True)
    copies = models.JSONField(default=list, blank=True)
    subject = models.CharField(max_length=255, blank=True)
    # Date de dépôt donnée par le serveur de messagerie, pas celle annoncée par l'expéditeur.
    received_at = models.DateTimeField()
    preview = models.CharField(max_length=200, blank=True)
    body_text = models.TextField(blank=True)
    # Écrit uniquement par apps.mailboxes.sanitizer.clean_html : jamais de HTML d'origine en base.
    body_html = models.TextField(blank=True)
    # Nom, type et taille seulement : aucun contenu de pièce jointe n'est stocké (pas de scan en V1).
    attachments = models.JSONField(default=list, blank=True)
    size = models.PositiveIntegerField(default=0)
    # Message trop volumineux ou illisible : seuls ses en-têtes ont été repris.
    partial = models.BooleanField(default=False)
    # Réponse automatique ou avis de non-remise : visible, mais sans notification par e-mail.
    automatic = models.BooleanField(default=False)
    synced_at = models.DateTimeField(auto_now_add=True)
    # État lu/non lu propre à Lionsmed et commun aux titulaires d'une boîte partagée.
    read_at = models.DateTimeField(null=True, blank=True)
    read_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-received_at", "-uid"]
        constraints = [
            models.UniqueConstraint(fields=["mailbox", "uid_validity", "uid"], name="inbound_email_uid_unique"),
            models.UniqueConstraint(fields=["mailbox", "fingerprint"], name="inbound_email_fingerprint_unique"),
        ]
        indexes = [models.Index(fields=["mailbox", "-received_at"], name="inbound_email_mailbox_idx")]


class OutgoingEmail(models.Model):
    """Message écrit dans Lionsmed depuis une boîte, immuable une fois placé dans l'outbox.

    L'état d'envoi n'est pas stocké ici : il se lit dans les lignes de l'outbox, une par destinataire."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mailbox = models.CharField(max_length=40)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="mailbox_messages")
    idempotency_key = models.UUIDField(unique=True)
    recipients = models.JSONField(default=list)
    copies = models.JSONField(default=list, blank=True)
    subject = models.CharField(max_length=180)
    body = models.TextField(max_length=20000)
    in_reply_to = models.ForeignKey(InboundEmail, on_delete=models.SET_NULL, null=True, blank=True, related_name="replies")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "id"]
        indexes = [models.Index(fields=["mailbox", "-created_at"], name="outgoing_email_mailbox_idx")]
