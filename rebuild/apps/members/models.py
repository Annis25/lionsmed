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
    # Profil public (recette V1) : opt-in strictement indépendant des permissions de
    # l'annuaire privé ci-dessus. Jamais activé par défaut, jamais de coordonnées exposées.
    public_profile_enabled = models.BooleanField(default=False)
    public_slug = models.SlugField(max_length=160, null=True, blank=True, unique=True)
    # Désignation individuelle (indépendante du rôle) : un membre peut être nommé
    # responsable des votes sans devenir PRESIDENT/SECRETAIRE/SUPER_ADMIN pour autant.
    is_vote_manager = models.BooleanField(default=False)
    # Abonnement calendrier (iCalendar) : jeton opaque, aléatoire, jamais l'UUID du
    # compte ni l'email. Régénérer écrase l'ancien, qui devient aussitôt invalide.
    calendar_token = models.CharField(max_length=43, null=True, blank=True, unique=True, editable=False)
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
    start_year = models.PositiveSmallIntegerField(help_text="Année de début")
    end_year = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Année de fin, vide si poste actuel")
    description = models.TextField(max_length=1500, blank=True)
    achievements = models.TextField(max_length=1500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_year", "id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(network__in=["LIONS", "LEO"]), name="experience_network_valid"),
            models.CheckConstraint(condition=models.Q(end_year__isnull=True) | models.Q(end_year__gte=models.F("start_year")), name="experience_years_ordered"),
        ]


class MembershipApplication(models.Model):
    import uuid
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    submission_key=models.UUIDField(unique=True)
    first_name=models.CharField(max_length=150)
    last_name=models.CharField(max_length=150)
    email=models.EmailField()
    phone=models.CharField(max_length=32,help_text="Obligatoire pour vous recontacter au sujet de votre candidature.")
    profession=models.CharField(max_length=150,blank=True)
    motivation=models.TextField(max_length=5000)
    origin=models.CharField(max_length=40,blank=True)
    state=models.CharField(max_length=12,choices=[("RECEIVED","Reçue"),("CONTACTED","Contact établi"),("FOLLOW_UP","En suivi"),("CLOSED","Close")],default="RECEIVED")
    notice_version=models.CharField(max_length=32,default="lot3-v1")
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        ordering=["-created_at","id"]
        constraints=[models.CheckConstraint(condition=models.Q(state__in=["RECEIVED","CONTACTED","FOLLOW_UP","CLOSED"]),name="application_state_valid")]
