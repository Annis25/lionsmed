from django.urls import path
from django.contrib.auth import views as auth
from django.views.generic import TemplateView
from apps.core.permissions import capability_required
from . import views

app_name = "accounts"
urlpatterns = [
    path("connexion/", views.LoginView.as_view(), name="login"),
    path("connexion/verification/", views.mfa_verify, name="mfa_verify"),
    path("espace/authentification-forte/", views.mfa_setup, name="mfa_setup"),
    path("deconnexion/", auth.LogoutView.as_view(), name="logout"),
    path("mot-de-passe-oublie/", views.PasswordResetView.as_view(), name="reset"),
    path("mot-de-passe-oublie/demande-recue/", TemplateView.as_view(template_name="accounts/reset_done.html"), name="reset_done"),
    path("reinitialiser/<uidb64>/<token>/", views.PasswordResetConfirmView.as_view(), name="reset_confirm"),
    path("mot-de-passe-reinitialise/", TemplateView.as_view(template_name="accounts/reset_complete.html"), name="reset_complete"),
    path("espace/mot-de-passe/", views.PasswordChangeView.as_view(), name="password_change"),
    path("espace/mot-de-passe/modifie/", capability_required("account.change_own_password")(
        TemplateView.as_view(template_name="accounts/password_change_done.html")), name="password_change_done"),
]
