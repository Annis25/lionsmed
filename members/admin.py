from django.contrib import admin
from .models import Cotisation, Document


@admin.register(Cotisation)
class CotisationAdmin(admin.ModelAdmin):
    list_display = ['member', 'year', 'amount', 'status', 'payment_date']
    list_filter = ['status', 'year']
    list_editable = ['status']
    search_fields = ['member__first_name', 'member__last_name', 'member__email']


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'visible_to', 'uploaded_by', 'uploaded_at']
    list_filter = ['category', 'visible_to']
