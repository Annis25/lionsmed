from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateRangeField, DateTimeRangeField, RangeOperators
from django.db import models
from django.db.models import Q, F, Func, Value


class Role(models.TextChoices):
    SUPER_ADMIN = "SUPER_ADMIN", "Super administrateur"
    DIRECTEUR = "DIRECTEUR", "Directeur"
    PRESIDENT = "PRESIDENT", "Président"
    SECRETAIRE = "SECRETAIRE", "Secrétaire"
    BUREAU = "BUREAU", "Bureau"
    MEMBRE = "MEMBRE", "Membre"
    INVITE = "INVITE", "Invité"


class LionsYear(models.Model):
    starts_on = models.DateField(unique=True)
    ends_on = models.DateField(help_text="Borne de fin exclusive")
    archived_at = models.DateTimeField(null=True, blank=True)

    @property
    def label(self):
        return f"{self.starts_on.year}–{self.ends_on.year}"

    def __str__(self):
        return self.label

    class Meta:
        ordering = ["-starts_on"]
        constraints = [
            models.CheckConstraint(condition=Q(ends_on__gt=F("starts_on")), name="year_dates_ordered"),
            ExclusionConstraint(name="year_no_overlap", expressions=[
                (Func("starts_on", "ends_on", Value("[)"), function="DATERANGE", output_field=DateRangeField()), RangeOperators.OVERLAPS),
            ]),
        ]


class ClubState(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    active_year = models.ForeignKey(LionsYear, on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(id=1), name="club_state_singleton")]


class RoleGrant(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="role_grants")
    role = models.CharField(max_length=16, choices=Role.choices)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    granted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="issued_grants")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["user", "starts_at"], name="grant_user_start_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(role__in=Role.values), name="grant_role_valid"),
            models.CheckConstraint(condition=Q(ends_at__isnull=True) | Q(ends_at__gt=F("starts_at")), name="grant_dates_ordered"),
            ExclusionConstraint(name="grant_no_overlap", condition=Q(revoked_at__isnull=True), expressions=[
                ("user", RangeOperators.EQUAL),
                (Func("starts_at", "ends_at", Value("[)"), function="TSTZRANGE", output_field=DateTimeRangeField()), RangeOperators.OVERLAPS),
            ]),
        ]


class Mandate(models.Model):
    import uuid
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey("members.MemberProfile", on_delete=models.PROTECT, related_name="mandates")
    function = models.CharField(max_length=150)
    lions_year = models.ForeignKey(LionsYear, on_delete=models.PROTECT, related_name="mandates")
    starts_on = models.DateField()
    ends_on = models.DateField(help_text="Borne de fin exclusive")
    validated_at = models.DateTimeField(null=True, blank=True)
    validated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    public_authorized = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        from django.core.exceptions import ValidationError
        super().clean()
        if self.lions_year_id and self.starts_on and self.ends_on:
            if not self.lions_year.starts_on <= self.starts_on < self.ends_on <= self.lions_year.ends_on:
                raise ValidationError("Le mandat doit être compris dans son Année Lions.")

    class Meta:
        ordering = ["-starts_on", "id"]
        constraints = [models.CheckConstraint(condition=Q(ends_on__gt=F("starts_on")), name="mandate_dates_ordered"),
            models.CheckConstraint(condition=(Q(validated_at__isnull=True, validated_by__isnull=True) | Q(validated_at__isnull=False, validated_by__isnull=False)), name="mandate_validation_pair")]
