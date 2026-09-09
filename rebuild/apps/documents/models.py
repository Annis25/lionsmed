import uuid
from django.conf import settings
from django.db import models


class Document(models.Model):
    class Category(models.TextChoices):
        GENERAL = "GENERAL", "Général"
        GOUVERNANCE = "GOUVERNANCE", "Gouvernance"
        FINANCIER = "FINANCIER", "Financier"
        DISTRICT = "DISTRICT", "District"
        AUTRE = "AUTRE", "Autre"

    class Visibility(models.TextChoices):
        MEMBERS = "MEMBERS", "Membres"
        BUREAU = "BUREAU", "Bureau"
        RESPONSABLES = "RESPONSABLES", "Responsables"

    class Status(models.TextChoices):
        QUARANTINE = "QUARANTINE", "En quarantaine"
        AVAILABLE = "AVAILABLE", "Disponible"
        REJECTED = "REJECTED", "Rejeté"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=180)
    description = models.TextField(max_length=2000, blank=True)
    category = models.CharField(max_length=15, choices=Category.choices, default=Category.GENERAL)
    visibility = models.CharField(max_length=15, choices=Visibility.choices, default=Visibility.MEMBERS)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUARANTINE)
    storage_key = models.CharField(max_length=120, editable=False)
    original_filename = models.CharField(max_length=255, editable=False)
    content_type = models.CharField(max_length=100, editable=False)
    size = models.PositiveIntegerField(editable=False)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="documents_authored")
    lions_year = models.ForeignKey("governance.LionsYear", on_delete=models.PROTECT, null=True, blank=True, related_name="documents")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(category__in=["GENERAL", "GOUVERNANCE", "FINANCIER", "DISTRICT", "AUTRE"]), name="document_category_valid"),
            models.CheckConstraint(condition=models.Q(visibility__in=["MEMBERS", "BUREAU", "RESPONSABLES"]), name="document_visibility_valid"),
            models.CheckConstraint(condition=models.Q(status__in=["QUARANTINE", "AVAILABLE", "REJECTED"]), name="document_status_valid"),
        ]


class DocumentGrant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="grants")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="document_grants")
    expires_at = models.DateTimeField(null=True, blank=True)
    granted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="document_grants_issued")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["document", "user"], name="document_grant_unique_document_user")]
