from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError


class SiteConfig(models.Model):
    """Configuration globale du site — une seule instance (singleton)"""
    name = models.CharField(
        max_length=100,
        default="Lions Club Sfax Méditerranée",
        verbose_name="Nom du club"
    )
    founded_year = models.IntegerField(
        default=2025,
        verbose_name="Année de fondation"
    )
    email_contact = models.EmailField(
        default="secretariat@lionsmed.tn",
        verbose_name="Email de contact"
    )
    phone_contact = models.CharField(
        max_length=20,
        default="+216 00 000 000",
        verbose_name="Téléphone de contact"
    )
    address = models.CharField(
        max_length=200,
        default="Sfax — Tunisie",
        verbose_name="Adresse du club"
    )
    monthly_meeting_day = models.CharField(
        max_length=100,
        default="2e lundi de chaque mois",
        verbose_name="Jour des réunions mensuelles",
        help_text="Ex: 2e lundi de chaque mois"
    )
    monthly_meeting_time = models.TimeField(
        default="19:00",
        verbose_name="Heure des réunions mensuelles"
    )
    mission_text = models.TextField(
        default="",
        verbose_name="Texte de la mission",
        blank=True
    )
    vision_text = models.TextField(
        default="",
        verbose_name="Texte de la vision",
        blank=True
    )
    history_intro = models.TextField(
        default="",
        verbose_name="Introduction historique",
        blank=True
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Dernière mise à jour"
    )

    class Meta:
        verbose_name = "Configuration du Site"
        verbose_name_plural = "Configuration du Site"

    def clean(self):
        """Empêche la création d'un 2e enregistrement"""
        if SiteConfig.objects.exists() and not self.pk:
            raise ValidationError("Une configuration existe déjà. Veuillez la modifier au lieu de créer une nouvelle.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def get_config(cls):
        """Récupère (ou crée) la configuration unique du site"""
        config, created = cls.objects.get_or_create(pk=1)
        return config

    def __str__(self):
        return f"Configuration - {self.name}"


class DomainAction(models.Model):
    """Domaines d'action du club — remplace les 6 domaines hardcodés"""
    ICON_CHOICES = [
        ('eye', 'Œil — Vision'),
        ('heart', 'Cœur — Santé'),
        ('graduation-cap', 'Mortier — Éducation'),
        ('leaf', 'Feuille — Environnement'),
        ('moon', 'Lune — Lutte contre la faim'),
        ('zap', 'Éclair — Aide d\'urgence'),
    ]
    COLOR_CHOICES = [
        ('blue', 'Bleu'),
        ('red', 'Rouge'),
        ('amber', 'Ambre'),
        ('green', 'Vert'),
        ('orange', 'Orange'),
        ('purple', 'Violet'),
    ]

    title = models.CharField(
        max_length=100,
        verbose_name="Titre du domaine"
    )
    description = models.TextField(
        verbose_name="Description détaillée"
    )
    icon = models.CharField(
        max_length=20,
        choices=ICON_CHOICES,
        verbose_name="Icône"
    )
    color = models.CharField(
        max_length=20,
        choices=COLOR_CHOICES,
        verbose_name="Couleur"
    )
    stat_label = models.CharField(
        max_length=100,
        verbose_name="Label de statut",
        help_text="Ex: 'Actions à venir', 'Prévention de proximité'"
    )
    order = models.IntegerField(
        default=0,
        verbose_name="Ordre d'affichage",
        help_text="Les domaines sont triés par ce champ"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Actif"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de modification"
    )

    class Meta:
        ordering = ['order', 'title']
        verbose_name = "Domaine d'Action"
        verbose_name_plural = "Domaines d'Action"

    def __str__(self):
        return self.title


class ClubStats(models.Model):
    """Statistiques du club pour une année donnée — résout les contradictions de données"""
    year = models.IntegerField(
        unique=True,
        verbose_name="Année"
    )
    members_count = models.IntegerField(
        default=0,
        verbose_name="Nombre de membres"
    )
    projects_count = models.IntegerField(
        default=0,
        verbose_name="Nombre de projets"
    )
    beneficiaries_count = models.IntegerField(
        default=0,
        verbose_name="Nombre de bénéficiaires"
    )
    years_of_existence = models.IntegerField(
        default=1,
        verbose_name="Années d'existence",
        help_text="Depuis la fondation du club en 2025"
    )
    last_updated = models.DateTimeField(
        auto_now=True,
        verbose_name="Dernière mise à jour"
    )

    class Meta:
        ordering = ['-year']
        verbose_name = "Statistique du Club"
        verbose_name_plural = "Statistiques du Club"

    @classmethod
    def get_latest(cls):
        """Stats de l'année courante, sinon la plus récente, sinon None si la base est vide"""
        from django.utils import timezone
        current_year = timezone.now().year
        try:
            return cls.objects.get(year=current_year)
        except cls.DoesNotExist:
            return cls.objects.order_by('-year').first()

    def __str__(self):
        return f"Stats {self.year} — {self.members_count} membres, {self.projects_count} projets"


class ClubValue(models.Model):
    """Valeurs fondamentales du club"""
    title = models.CharField(
        max_length=100,
        verbose_name="Titre de la valeur"
    )
    description = models.TextField(
        verbose_name="Description de la valeur"
    )
    icon_svg_name = models.CharField(
        max_length=50,
        verbose_name="Nom de l'icône SVG",
        help_text="Ex: 'heart', 'shield', 'users', etc."
    )
    tagline = models.CharField(
        max_length=200,
        verbose_name="Slogan/Tagline",
        help_text="Ex: 'We Serve', 'Éthique absolue'"
    )
    order = models.IntegerField(
        default=0,
        verbose_name="Ordre d'affichage"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de modification"
    )

    class Meta:
        ordering = ['order']
        verbose_name = "Valeur du Club"
        verbose_name_plural = "Valeurs du Club"

    def __str__(self):
        return self.title


class HistoricalMilestone(models.Model):
    """Jalons historiques du club — remplace la timeline hardcodée"""
    year = models.IntegerField(
        verbose_name="Année"
    )
    title = models.CharField(
        max_length=200,
        verbose_name="Titre du jalon"
    )
    description = models.TextField(
        verbose_name="Description du jalon"
    )
    is_active_milestone = models.BooleanField(
        default=False,
        verbose_name="Jalon actif",
        help_text="Mettre en évidence ce jalon comme important"
    )
    order = models.IntegerField(
        default=0,
        verbose_name="Ordre d'affichage"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de modification"
    )

    class Meta:
        ordering = ['year']
        verbose_name = "Jalon Historique"
        verbose_name_plural = "Jalons Historiques"

    def __str__(self):
        return f"{self.year} — {self.title}"


class BureauMember(models.Model):
    """Profils détaillés du bureau du club — lié aux User existants"""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bureau_profile',
        verbose_name="Utilisateur du club",
        help_text="Sélectionnez un utilisateur avec rôle BUREAU, PRESIDENT, etc."
    )
    bio = models.TextField(
        verbose_name="Biographie détaillée",
        blank=True,
        help_text="Description professionnelle et personnelle"
    )
    role_description = models.CharField(
        max_length=200,
        verbose_name="Fonction au sein du bureau",
        blank=True,
        help_text="Ex: 'Coordinatrice du programme Vision'"
    )
    linkedin_url = models.URLField(
        verbose_name="URL LinkedIn",
        blank=True
    )
    email_bureau = models.EmailField(
        verbose_name="Email du bureau",
        blank=True,
        help_text="Email personnel du membre (optionnel)"
    )
    order = models.IntegerField(
        default=0,
        verbose_name="Ordre d'affichage"
    )
    is_visible = models.BooleanField(
        default=True,
        verbose_name="Visible sur le site"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de modification"
    )

    class Meta:
        ordering = ['order']
        verbose_name = "Membre du Bureau"
        verbose_name_plural = "Membres du Bureau"

    @property
    def initials(self):
        """Initiales affichées dans les cartes du bureau (fallback quand il n'y a pas de photo)"""
        parts = [self.user.first_name, self.user.last_name]
        return ''.join(p[0].upper() for p in parts if p) or '?'

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.user.get_role_display()})"


class MembershipBenefit(models.Model):
    """Avantages de l'adhésion — affichés sur la page d'accueil et à-propos"""
    title = models.CharField(
        max_length=150,
        verbose_name="Titre de l'avantage"
    )
    description = models.TextField(
        verbose_name="Description de l'avantage"
    )
    icon_name = models.CharField(
        max_length=50,
        verbose_name="Nom de l'icône",
        help_text="Ex: 'users', 'zap', 'book', 'star'"
    )
    order = models.IntegerField(
        default=0,
        verbose_name="Ordre d'affichage"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Actif"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de modification"
    )

    class Meta:
        ordering = ['order']
        verbose_name = "Avantage de l'Adhésion"
        verbose_name_plural = "Avantages de l'Adhésion"

    def __str__(self):
        return self.title
