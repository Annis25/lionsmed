from django.conf import settings
from django.db import models


class MemberProfile(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Membre actif"
        GUEST = "GUEST", "Invité"
        SUSPENDED = "SUSPENDED", "Suspendu"
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="member_profile")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.GUEST)
    phone = models.CharField(max_length=32, blank=True)
    profession = models.CharField(max_length=150, blank=True)
    bio = models.TextField(max_length=1000, blank=True)
    photo_key = models.CharField(max_length=100, blank=True, editable=False)
    directory_visible = models.BooleanField(default=False)
    share_profession = models.BooleanField(default=False)
    share_bio = models.BooleanField(default=False)
    share_contacts = models.BooleanField(default=False)
    share_photo = models.BooleanField(default=False)
    share_experiences = models.BooleanField(default=False)
    share_mandates = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(status__in=["ACTIVE", "GUEST", "SUSPENDED"]), name="profile_status_valid")]


class AssociationExperience(models.Model):
    import uuid
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(MemberProfile, on_delete=models.PROTECT, related_name="experiences")
    network = models.CharField(max_length=5, choices=[("LIONS", "Lions"), ("LEO", "LEO")])
    club = models.CharField(max_length=150)
    function = models.CharField(max_length=150)
    district = models.CharField(max_length=100, blank=True)
    starts_on = models.DateField(help_text="Mois de début, enregistré au premier jour")
    ends_on = models.DateField(null=True, blank=True, help_text="Mois de fin inclus")
    description = models.TextField(max_length=1500, blank=True)
    achievements = models.TextField(max_length=1500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-starts_on", "id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(network__in=["LIONS", "LEO"]), name="experience_network_valid"),
            models.CheckConstraint(condition=models.Q(ends_on__isnull=True) | models.Q(ends_on__gte=models.F("starts_on")), name="experience_dates_ordered"),
            models.CheckConstraint(condition=models.Q(starts_on__day=1) & (models.Q(ends_on__isnull=True) | models.Q(ends_on__day=1)), name="experience_month_precision"),
        ]
