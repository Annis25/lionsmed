import uuid
from django.conf import settings
from django.db import models


class DuesSchedule(models.Model):
    """Montants des deux tranches pour une Année Lions donnée — définis une seule fois
    par le trésorier, communs à tous les membres (jamais de montant par membre)."""
    lions_year = models.OneToOneField("governance.LionsYear", on_delete=models.PROTECT, related_name="dues_schedule")
    tranche1_amount = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="Montant de la tranche 1 (6 premiers mois), en TND — laissé vide tant qu'il n'est pas fixé.")
    tranche2_amount = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="Montant de la tranche 2 (6 derniers mois), en TND — laissé vide tant qu'il n'est pas fixé.")
    currency = models.CharField(max_length=3, default="TND")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="dues_schedules_updated")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(tranche1_amount__isnull=True) | models.Q(tranche1_amount__gte=0), name="dues_schedule_t1_non_negative"),
            models.CheckConstraint(condition=models.Q(tranche2_amount__isnull=True) | models.Q(tranche2_amount__gte=0), name="dues_schedule_t2_non_negative"),
        ]


class DuesRecord(models.Model):
    """Une ligne par membre et par Année Lions. Deux tranches indépendantes : un membre
    n'ayant réglé que la tranche 1 n'est jamais considéré à jour."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey("members.MemberProfile", on_delete=models.PROTECT, related_name="dues_records")
    lions_year = models.ForeignKey("governance.LionsYear", on_delete=models.PROTECT, related_name="dues_records")
    tranche1_paid = models.BooleanField(default=False)
    tranche1_paid_on = models.DateField(null=True, blank=True)
    tranche2_paid = models.BooleanField(default=False)
    tranche2_paid_on = models.DateField(null=True, blank=True)
    note = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-lions_year__starts_on"]
        constraints = [
            models.UniqueConstraint(fields=["profile", "lions_year"], name="dues_unique_profile_year"),
        ]

    @property
    def status(self):
        if self.tranche1_paid and self.tranche2_paid:
            return "PAID"
        if self.tranche1_paid or self.tranche2_paid:
            return "PARTIAL"
        return "TO_REGULARIZE"

    STATUS_LABELS = {"PAID": "Payé", "PARTIAL": "Partiellement payé", "TO_REGULARIZE": "Non payé"}

    @property
    def status_label(self):
        return self.STATUS_LABELS[self.status]


class DuesChange(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    record = models.ForeignKey(DuesRecord, on_delete=models.PROTECT, related_name="changes")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="dues_changes_made")
    tranche = models.PositiveSmallIntegerField()
    old_paid = models.BooleanField()
    new_paid = models.BooleanField()
    motif = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.CheckConstraint(condition=models.Q(tranche__in=[1, 2]), name="dues_change_tranche_valid")]
