from django.contrib import admin
from .models import Notification, EmailReminder


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['recipient', 'notif_type', 'title', 'is_read', 'created_at']
    list_filter = ['notif_type', 'is_read']
    list_editable = ['is_read']


@admin.register(EmailReminder)
class EmailReminderAdmin(admin.ModelAdmin):
    list_display = ['event', 'reminder_type', 'is_sent', 'sent_at']
    list_filter = ['reminder_type', 'is_sent']
