from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, MembershipRequest


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ['username', 'email', 'get_full_name', 'role', 'is_approved', 'is_active']
    list_filter = ['role', 'is_approved', 'is_active']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    list_editable = ['role', 'is_approved']
    fieldsets = UserAdmin.fieldsets + (
        ('Informations Lions Club', {
            'fields': ('role', 'phone', 'bio', 'photo', 'date_joined_club', 'is_approved', 'profession')
        }),
    )


@admin.register(MembershipRequest)
class MembershipRequestAdmin(admin.ModelAdmin):
    list_display = ['first_name', 'last_name', 'email', 'profession', 'status', 'created_at']
    list_filter = ['status']
    list_editable = ['status']
    search_fields = ['first_name', 'last_name', 'email']
