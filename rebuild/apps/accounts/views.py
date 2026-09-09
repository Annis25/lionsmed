from urllib.parse import urlsplit
from django.conf import settings
from django.contrib.auth import get_user_model, login as auth_login, views as auth_views
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.shortcuts import render, redirect
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods
from apps.core.permissions import capability_required, effective_role, MANAGERS
from apps.core.throttling import consume
from . import mfa
from .forms import LoginForm, ResetForm, NewPasswordForm, ChangePasswordForm, MfaVerifyForm, MfaConfirmForm, MfaDisableForm
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
        user = form.get_user()
        if effective_role(user) in MANAGERS and mfa.has_confirmed_device(user):
            # Session partielle : le compte n'est authentifié qu'après le second facteur.
            self.request.session["mfa_user_id"] = str(user.pk)
            self.request.session["mfa_remember"] = bool(form.cleaned_data["remember"])
            return HttpResponseRedirect(reverse("accounts:mfa_verify"))
        response = super().form_valid(form)
        self.request.session.set_expiry(settings.SESSION_COOKIE_AGE if form.cleaned_data["remember"] else 0)
        return response


@require_http_methods(["GET", "POST"])
def mfa_verify(request):
    user_id = request.session.get("mfa_user_id")
    if not user_id:
        return redirect("accounts:login")
    try:
        user = get_user_model().objects.get(pk=user_id, is_active=True)
    except get_user_model().DoesNotExist:
        del request.session["mfa_user_id"]
        return redirect("accounts:login")
    form = MfaVerifyForm(request.POST or None)
    if request.method == "POST":
        if not consume("mfa-verify", str(user.pk), limit=10, seconds=900):
            return lockout(request)
        if form.is_valid() and mfa.verify_login_token(user, form.cleaned_data["token"]):
            remember = request.session.pop("mfa_remember", False)
            del request.session["mfa_user_id"]
            auth_login(request, user, backend="apps.accounts.backends.EmailBackend")
            request.session.set_expiry(settings.SESSION_COOKIE_AGE if remember else 0)
            return redirect(settings.LOGIN_REDIRECT_URL)
        form.add_error(None, "Code invalide.")
    return render(request, "accounts/mfa_verify.html", {"form": form})


@capability_required("mfa.manage_own")
@require_http_methods(["GET", "POST"])
def mfa_setup(request):
    user = request.user
    if mfa.has_confirmed_device(user):
        if request.method == "POST":
            form = MfaDisableForm(request.POST, user=user)
            if form.is_valid():
                mfa.disable(user=user, actor=user)
                return redirect("accounts:mfa_setup")
        else:
            form = MfaDisableForm(user=user)
        return render(request, "espace/mfa_setup.html", {"enabled": True, "form": form})
    device = mfa.get_or_create_pending_device(user)
    codes = None
    form = MfaConfirmForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            codes = mfa.confirm_device(user=user, device=device, token=form.cleaned_data["token"])
        except ValidationError as error:
            form.add_error("token", error)
    uri = mfa.provisioning_uri(device, user.email)
    return render(request, "espace/mfa_setup.html", {
        "enabled": False, "form": form, "codes": codes,
        "qr_data_uri": mfa.qr_data_uri(uri), "secret": mfa.base32_secret(device),
    })


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
                subject_template_name=self.subject_template_name,
                extra_email_context={"site_origin": settings.SITE_ORIGIN})
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
