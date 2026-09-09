from urllib.parse import urlsplit
from django.conf import settings
from django.contrib.auth import views as auth_views
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters
from apps.core.permissions import capability_required
from apps.core.throttling import consume
from .forms import LoginForm, ResetForm, NewPasswordForm, ChangePasswordForm
from .models import normalize_email


def lockout(request, credentials=None, *args, **kwargs):
    response = render(request, "accounts/limited.html", status=429)
    response["Retry-After"] = "900"
    return response


@method_decorator(sensitive_post_parameters(), name="dispatch")
class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm

    def post(self, request, *args, **kwargs):
        # REMOTE_ADDR uniquement ; ne pas faire confiance à X-Forwarded-For.
        if not consume("login-ip", request.META.get("REMOTE_ADDR", "unknown"), limit=20, seconds=900):
            return lockout(request)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        self.request.session.set_expiry(settings.SESSION_COOKIE_AGE if form.cleaned_data["remember"] else 0)
        return response


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "accounts/reset.html"
    form_class = ResetForm
    email_template_name = "emails/password_reset.txt"
    html_email_template_name = "emails/password_reset.html"
    subject_template_name = "emails/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:reset_done")

    def post(self, request, *args, **kwargs):
        if not consume("reset-ip", request.META.get("REMOTE_ADDR", "unknown"), limit=5, seconds=900):
            return lockout(request)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        from django.http import HttpResponseRedirect
        # Adresse connue ou inconnue : même compteur et même réponse.
        if consume("reset-email", normalize_email(form.cleaned_data["email"]), limit=3, seconds=3600):
            origin = urlsplit(settings.SITE_ORIGIN)
            form.save(use_https=origin.scheme == "https", domain_override=origin.netloc,
                request=self.request, from_email=settings.DEFAULT_FROM_EMAIL,
                email_template_name=self.email_template_name,
                html_email_template_name=self.html_email_template_name,
                subject_template_name=self.subject_template_name)
        return HttpResponseRedirect(self.success_url)


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "accounts/reset_confirm.html"
    form_class = NewPasswordForm
    success_url = reverse_lazy("accounts:reset_complete")
    post_reset_login = False


@method_decorator(capability_required("account.change_own_password"), name="dispatch")
class PasswordChangeView(auth_views.PasswordChangeView):
    template_name = "accounts/password_change.html"
    form_class = ChangePasswordForm
    success_url = reverse_lazy("accounts:password_change_done")
