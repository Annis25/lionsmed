from django.contrib.auth.models import AbstractUser
from django.db import models

from core.validators import IMAGE_VALIDATORS


class User(AbstractUser):
    ROLE_CHOICES = [
        ('SUPER_ADMIN', 'Super Admin'),
        ('PAST_PRESIDENT', 'Past Président'),
        ('PRESIDENT', 'Président'),
        ('BUREAU', 'Bureau'),
        ('COMITE', 'Comité'),
        ('MEMBRE', 'Membre'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='MEMBRE')
    phone = models.CharField(max_length=20, blank=True)
    bio = models.TextField(blank=True)
    photo = models.ImageField(
        upload_to='members/', blank=True, null=True, validators=IMAGE_VALIDATORS
    )
    date_joined_club = models.DateField(null=True, blank=True)
    is_approved = models.BooleanField(default=False)
    profession = models.CharField(max_length=100, blank=True)

    def save(self, *args, **kwargs):
        # L'adresse est normalisée en minuscules à l'enregistrement : la casse
        # ne désigne jamais deux boîtes différentes en pratique, et la laisser
        # varier ferait échouer les recherches strictes (connexion, doublons).
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_full_name()} ({self.role})"

    @property
    def is_bureau_or_above(self):
        return self.role in ['SUPER_ADMIN', 'PAST_PRESIDENT', 'PRESIDENT', 'BUREAU']

    @property
    def can_publish(self):
        return self.role in ['SUPER_ADMIN', 'PAST_PRESIDENT', 'PRESIDENT', 'BUREAU', 'COMITE']


class MembershipRequest(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'En attente'),
        ('APPROVED', 'Approuvée'),
        ('REJECTED', 'Refusée'),
    ]
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20)
    profession = models.CharField(max_length=100)
    motivation = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name='reviewed_requests'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        # Même normalisation que sur User : l'unicité de ce champ est appliquée
        # par la base, et sans normalisation « Jean@x.tn » passerait à côté d'une
        # candidature déjà déposée avec « jean@x.tn ».
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.status}"
