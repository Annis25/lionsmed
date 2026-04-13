from django.contrib import admin
from .models import (
    SiteConfig, DomainAction, ClubStats, ClubValue,
    HistoricalMilestone, BureauMember, MembershipBenefit
)


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    list_display = ('name', 'founded_year', 'email_contact', 'phone_contact', 'updated_at')
    fieldsets = (
        ('Identité du Club', {
            'fields': ('name', 'founded_year', 'address')
        }),
        ('Contact', {
            'fields': ('email_contact', 'phone_contact')
        }),
        ('Réunions Mensuelles', {
            'fields': ('monthly_meeting_day', 'monthly_meeting_time')
        }),
        ('Contenu', {
            'fields': ('mission_text', 'vision_text', 'history_intro')
        }),
    )
    readonly_fields = ('updated_at',)

    def has_add_permission(self, request):
        """Empêche l'ajout d'une nouvelle configuration"""
        return False

    def has_delete_permission(self, request, obj=None):
        """Empêche la suppression de la configuration"""
        return False


@admin.register(DomainAction)
class DomainActionAdmin(admin.ModelAdmin):
    list_display = ('title', 'icon', 'color', 'order', 'is_active')
    list_editable = ('order', 'is_active')
    list_filter = ('is_active', 'color')
    search_fields = ('title', 'description')
    fieldsets = (
        ('Domaine', {
            'fields': ('title', 'description')
        }),
        ('Présentation', {
            'fields': ('icon', 'color', 'stat_label')
        }),
        ('Gestion', {
            'fields': ('order', 'is_active')
        }),
    )
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ClubStats)
class ClubStatsAdmin(admin.ModelAdmin):
    list_display = ('year', 'members_count', 'projects_count', 'beneficiaries_count', 'years_of_existence')
    list_filter = ('year',)
    search_fields = ('year',)
    fieldsets = (
        ('Année', {
            'fields': ('year',)
        }),
        ('Statistiques', {
            'fields': ('members_count', 'projects_count', 'beneficiaries_count', 'years_of_existence')
        }),
    )
    readonly_fields = ('last_updated',)


@admin.register(ClubValue)
class ClubValueAdmin(admin.ModelAdmin):
    list_display = ('title', 'tagline', 'order')
    list_editable = ('order',)
    search_fields = ('title', 'description')
    fieldsets = (
        ('Valeur', {
            'fields': ('title', 'description')
        }),
        ('Présentation', {
            'fields': ('icon_svg_name', 'tagline')
        }),
        ('Gestion', {
            'fields': ('order',)
        }),
    )
    readonly_fields = ('created_at', 'updated_at')


@admin.register(HistoricalMilestone)
class HistoricalMilestoneAdmin(admin.ModelAdmin):
    list_display = ('year', 'title', 'is_active_milestone', 'order')
    list_editable = ('is_active_milestone', 'order')
    list_filter = ('year', 'is_active_milestone')
    search_fields = ('title', 'description', 'year')
    fieldsets = (
        ('Jalon', {
            'fields': ('year', 'title', 'description')
        }),
        ('Gestion', {
            'fields': ('is_active_milestone', 'order')
        }),
    )
    readonly_fields = ('created_at', 'updated_at')


@admin.register(BureauMember)
class BureauMemberAdmin(admin.ModelAdmin):
    list_display = ('get_full_name', 'get_role', 'role_description', 'is_visible', 'order')
    list_editable = ('is_visible', 'order')
    list_filter = ('is_visible', 'user__role')
    search_fields = ('user__first_name', 'user__last_name', 'role_description')
    fieldsets = (
        ('Utilisateur', {
            'fields': ('user',)
        }),
        ('Profil du Bureau', {
            'fields': ('bio', 'role_description')
        }),
        ('Contact', {
            'fields': ('email_bureau', 'linkedin_url')
        }),
        ('Gestion', {
            'fields': ('order', 'is_visible')
        }),
    )
    readonly_fields = ('created_at', 'updated_at')

    def get_full_name(self, obj):
        return obj.user.get_full_name()
    get_full_name.short_description = 'Nom'

    def get_role(self, obj):
        return obj.user.get_role_display()
    get_role.short_description = 'Rôle'


@admin.register(MembershipBenefit)
class MembershipBenefitAdmin(admin.ModelAdmin):
    list_display = ('title', 'order', 'is_active')
    list_editable = ('order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('title', 'description')
    fieldsets = (
        ('Avantage', {
            'fields': ('title', 'description')
        }),
        ('Présentation', {
            'fields': ('icon_name',)
        }),
        ('Gestion', {
            'fields': ('order', 'is_active')
        }),
    )
    readonly_fields = ('created_at', 'updated_at')
