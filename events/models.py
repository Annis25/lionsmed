from django.db import models
from accounts.models import User


class Event(models.Model):
    TYPE_CHOICES = [
        ('REUNION', 'Réunion'),
        ('ACTION', 'Action sociale'),
        ('GALA', 'Gala/Soirée'),
        ('FORMATION', 'Formation'),
        ('AUTRE', 'Autre'),
    ]
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField()
    event_type = models.CharField(max_length=15, choices=TYPE_CHOICES, default='AUTRE')
    date_start = models.DateTimeField()
    date_end = models.DateTimeField(null=True, blank=True)
    location = models.CharField(max_length=200)
    image = models.ImageField(upload_to='events/', blank=True, null=True)
    price = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    is_public = models.BooleanField(default=True)
    is_payant = models.BooleanField(default=False)
    is_featured = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date_start']

    def __str__(self):
        return self.title


class EventRegistration(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'En attente'),
        ('CONFIRMED', 'Confirmé'),
        ('CANCELLED', 'Annulé'),
        ('ATTENDED', 'Présent'),
    ]
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='registrations')
    member = models.ForeignKey(User, on_delete=models.CASCADE, related_name='event_registrations')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    registered_at = models.DateTimeField(auto_now_add=True)
    is_paid = models.BooleanField(default=False)
    payment_ref = models.CharField(max_length=100, blank=True)

    class Meta:
        unique_together = ['event', 'member']

    def __str__(self):
        return f"{self.member} → {self.event}"
