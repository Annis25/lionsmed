from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm
from .models import User


class CreateAccountForm(AdminUserCreationForm):
    class Meta(AdminUserCreationForm.Meta):
        model = User
        fields = ("email",)


class ChangeAccountForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"


@admin.register(User)
class AccountAdmin(UserAdmin):
    add_form = CreateAccountForm
    form = ChangeAccountForm
    ordering = ("email",)
    list_display = ("email", "is_active", "is_staff")
    search_fields = ("email", "first_name", "last_name")
    fieldsets = ((None, {"fields": ("email", "password")}),
        ("Identité", {"fields": ("first_name", "last_name")}),
        ("Accès technique", {"fields": ("is_active", "is_staff", "is_superuser")}),
        ("Dates", {"fields": ("date_joined", "last_login", "updated_at")}))
    readonly_fields = ("date_joined", "last_login", "updated_at")
    add_fieldsets = ((None, {"fields": ("email", "usable_password", "password1", "password2")}),)

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_staff and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    has_add_permission = has_view_permission
    has_change_permission = has_view_permission

    def has_delete_permission(self, request, obj=None):
        return False
