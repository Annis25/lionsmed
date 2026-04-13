from django.db import models
from accounts.models import User


class Notification(models.Model):
    TYPE_CHOICES = [
        ('EVENT', 'Événement'),
        ('VOTE', 'Vote'),
        ('NEWS', 'Actualité'),
        ('SYSTEM', 'Système'),
        ('COTISATION', 'Cotisation'),
    ]
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    notif_type = models.CharField(max_length=15, choices=TYPE_CHOICES, default='SYSTEM')
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    link = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.recipient} - {self.title}"


class EmailReminder(models.Model):
    TYPE_CHOICES = [('J7', '7 jours avant'), ('J1', '1 jour avant')]
    event = models.ForeignKey('events.Event', on_delete=models.CASCADE, related_name='reminders')
    reminder_type = models.CharField(max_length=5, choices=TYPE_CHOICES)
    is_sent = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ['event', 'reminder_type']

    def __str__(self):
        return f"{self.event} - {self.reminder_type}"
