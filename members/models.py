from django.conf import settings
from django.db import models
from accounts.models import User

from core.validators import DOCUMENT_VALIDATORS


class Cotisation(models.Model):
    STATUS_CHOICES = [
        ('PAID', 'Payée'),
        ('PENDING', 'En attente'),
        ('OVERDUE', 'En retard'),
    ]
    member = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cotisations')
    year = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    payment_date = models.DateField(null=True, blank=True)
    payment_ref = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['member', 'year']

    def __str__(self):
        return f"{self.member} - {self.year} - {self.status}"


class Document(models.Model):
    CATEGORY_CHOICES = [
        ('PV', 'Procès-verbal'),
        ('RAPPORT', 'Rapport'),
        ('REGLEMENT', 'Règlement'),
        ('AUTRE', 'Autre'),
    ]
    VISIBLE_TO_CHOICES = [
        ('ALL', 'Tous les membres'),
        ('BUREAU', 'Bureau et plus'),
        ('PRESIDENT', 'Président et plus'),
        ('ADMIN', 'Admin seulement'),
    ]
    # Niveau requis pour chaque valeur de visible_to, et niveau accordé à chaque rôle.
    # Un rôle absent de ROLE_LEVELS ne reçoit aucun niveau : l'accès est alors refusé
    # (refus par défaut), au lieu de retomber sur le niveau le plus bas.
    VISIBILITY_LEVELS = {'ALL': 0, 'BUREAU': 2, 'PRESIDENT': 3, 'ADMIN': 5}
    ROLE_LEVELS = {
        'MEMBRE': 0,
        'COMITE': 1,
        'BUREAU': 2,
        'PRESIDENT': 3,
        'PAST_PRESIDENT': 4,
        'SUPER_ADMIN': 5,
    }

    title = models.CharField(max_length=200)
    # Stocké hors de MEDIA_ROOT : ces fichiers ne doivent jamais être servis
    # directement par le serveur web, seulement via la vue document_download.
    file = models.FileField(
        upload_to='documents/',
        storage=settings.PRIVATE_STORAGE,
        validators=DOCUMENT_VALIDATORS,
    )
    category = models.CharField(max_length=15, choices=CATEGORY_CHOICES, default='AUTRE')
    visible_to = models.CharField(max_length=15, choices=VISIBLE_TO_CHOICES, default='ALL')
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.title

    def is_visible_to(self, user):
        """Refus par défaut : rôle inconnu ou visibilité inconnue → pas d'accès."""
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        if not getattr(user, 'is_approved', False) or not user.is_active:
            return False
        user_level = self.ROLE_LEVELS.get(user.role)
        if user_level is None:
            return False
        required = self.VISIBILITY_LEVELS.get(self.visible_to)
        if required is None:
            return False
        return user_level >= required

    @classmethod
    def visible_for(cls, user):
        return [d for d in cls.objects.all() if d.is_visible_to(user)]
