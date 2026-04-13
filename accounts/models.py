from django.contrib.auth.models import AbstractUser
from django.db import models


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
    photo = models.ImageField(upload_to='members/', blank=True, null=True)
    date_joined_club = models.DateField(null=True, blank=True)
    is_approved = models.BooleanField(default=False)
    profession = models.CharField(max_length=100, blank=True)

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

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.status}"
