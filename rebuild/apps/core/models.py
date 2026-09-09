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


class PublicImage(models.Model):
    import uuid
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    small_key=models.CharField(max_length=100,editable=False)
    large_key=models.CharField(max_length=100,editable=False)
    width=models.PositiveIntegerField()
    height=models.PositiveIntegerField()
    alt=models.CharField(max_length=250)
    source=models.CharField(max_length=300)
    approved_at=models.DateTimeField(null=True,blank=True)
    uploaded_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return self.alt

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse("editorial:image",args=[self.pk,1024])
    def small_url(self):
        from django.urls import reverse
        return reverse("editorial:image",args=[self.pk,480])
