import uuid
from django.conf import settings
from django.db import models


class SatisfactionPeriod(models.Model):
    """`month` n'est jamais saisi : dérivé de opens_at (premier jour de son mois) à la
    création, pour un affichage/tri sans dupliquer une information déjà portée par
    opens_at/closes_at. Plusieurs consultations peuvent partager le même mois (plus
    unique depuis la demande explicite de pouvoir en ouvrir plusieurs en parallèle) :
    seule leur identité (id) est unique, jamais leur mois."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    month = models.DateField(help_text="Premier jour du mois concerné")
    title = models.CharField(max_length=180, blank=True)
    description = models.TextField(max_length=3000, blank=True)
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


class SatisfactionAxis(models.Model):
    period = models.ForeignKey(SatisfactionPeriod, on_delete=models.CASCADE, related_name="axes")
    label = models.CharField(max_length=180)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "pk"]


class SatisfactionAxisScore(models.Model):
    response = models.ForeignKey(SatisfactionResponse, on_delete=models.PROTECT, related_name="axis_scores")
    axis = models.ForeignKey(SatisfactionAxis, on_delete=models.PROTECT, related_name="scores")
    score = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["response", "axis"], name="satisfaction_unique_axis_score"),
            models.CheckConstraint(condition=models.Q(score__gte=1, score__lte=5), name="satisfaction_axis_score_range"),
        ]
