from django.contrib import admin
from .models import Event, EventRegistration


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ['title', 'event_type', 'date_start', 'location', 'is_public', 'is_payant', 'is_featured']
    list_filter = ['event_type', 'is_public', 'is_payant', 'is_featured']
    list_editable = ['is_featured', 'is_public']
    search_fields = ['title', 'location']
    prepopulated_fields = {'slug': ('title',)}
    date_hierarchy = 'date_start'


@admin.register(EventRegistration)
class EventRegistrationAdmin(admin.ModelAdmin):
    list_display = ['member', 'event', 'status', 'is_paid', 'registered_at']
    list_filter = ['status', 'is_paid']
    list_editable = ['status', 'is_paid']
