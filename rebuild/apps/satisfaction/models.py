import uuid
from django.conf import settings
from django.db import models


class SatisfactionPeriod(models.Model):
    """Une ligne par mois. opens_at/closes_at restent nuls tant que l'heure de référence
    n'est pas configurée : la période n'est alors pas activable (voir scheduling.compute_window)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    month = models.DateField(unique=True, help_text="Premier jour du mois concerné")
    rule_version = models.CharField(max_length=32)
    opens_at = models.DateTimeField(null=True, blank=True)
    closes_at = models.DateTimeField(null=True, blank=True)
    threshold = models.PositiveSmallIntegerField(default=5, help_text="Effectif minimal avant affichage des résultats — valeur de test, production À CONFIRMER HUMAINEMENT")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="satisfaction_periods_created")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-month"]
        constraints = [
            models.CheckConstraint(condition=models.Q(month__day=1), name="satisfaction_period_month_first_day"),
            models.CheckConstraint(condition=models.Q(opens_at__isnull=True) | models.Q(closes_at__isnull=True) | models.Q(closes_at__gt=models.F("opens_at")), name="satisfaction_period_dates_ordered"),
            models.CheckConstraint(condition=models.Q(threshold__gte=1), name="satisfaction_period_threshold_positive"),
        ]


class SatisfactionResponse(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    period = models.ForeignKey(SatisfactionPeriod, on_delete=models.PROTECT, related_name="responses")
    profile = models.ForeignKey("members.MemberProfile", on_delete=models.PROTECT, related_name="satisfaction_responses")
    score = models.PositiveSmallIntegerField()
    comment = models.TextField(max_length=1000, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["period", "profile"], name="satisfaction_unique_period_profile"),
            models.CheckConstraint(condition=models.Q(score__gte=1) & models.Q(score__lte=5), name="satisfaction_score_range"),
        ]
