from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    action = models.CharField(max_length=64)
    object_type = models.CharField(max_length=32)
    object_id = models.CharField(max_length=64)
    result = models.CharField(max_length=16, default="success")
    created_at = models.DateTimeField(auto_now_add=True)
    # Données bornées générées par services ; aucun payload/secret arbitraire.
    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["object_type", "object_id", "created_at"], name="audit_object_date_idx")]


class AuthThrottle(models.Model):
    """Compteur partagé PostgreSQL, clés HMAC, sans adresse/IP en clair."""
    key = models.CharField(max_length=64, primary_key=True)
    count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)
