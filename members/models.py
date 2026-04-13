from django.db import models
from accounts.models import User


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
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to='documents/')
    category = models.CharField(max_length=15, choices=CATEGORY_CHOICES, default='AUTRE')
    visible_to = models.CharField(max_length=15, choices=VISIBLE_TO_CHOICES, default='ALL')
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.title
