import uuid
from django.conf import settings
from django.db import models


class DuesRecord(models.Model):
    class Status(models.TextChoices):
        TO_REGULARIZE = "TO_REGULARIZE", "À régulariser"
        PAID = "PAID", "Réglée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey("members.MemberProfile", on_delete=models.PROTECT, related_name="dues_records")
    lions_year = models.ForeignKey("governance.LionsYear", on_delete=models.PROTECT, related_name="dues_records")
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.TO_REGULARIZE)
    amount = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, help_text="Montant en TND, laissé vide tant qu'il n'est pas connu")
    currency = models.CharField(max_length=3, default="TND")
    paid_on = models.DateField(null=True, blank=True)
    note = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-lions_year__starts_on"]
        constraints = [
            models.UniqueConstraint(fields=["profile", "lions_year"], name="dues_unique_profile_year"),
            models.CheckConstraint(condition=models.Q(status__in=["TO_REGULARIZE", "PAID"]), name="dues_status_valid"),
            models.CheckConstraint(condition=models.Q(amount__isnull=True) | models.Q(amount__gte=0), name="dues_amount_non_negative"),
        ]


class DuesChange(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    record = models.ForeignKey(DuesRecord, on_delete=models.PROTECT, related_name="changes")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="dues_changes_made")
    old_status = models.CharField(max_length=15)
    new_status = models.CharField(max_length=15)
    old_amount = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    new_amount = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    motif = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
