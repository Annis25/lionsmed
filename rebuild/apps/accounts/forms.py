import logging
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, SetPasswordForm, PasswordChangeForm
from django import forms
from django.core.mail import EmailMultiAlternatives
from django.template import loader
from .models import normalize_email

logger = logging.getLogger(__name__)


class StyledFields:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "champ__input"


class LoginForm(StyledFields, AuthenticationForm):
    username = forms.EmailField(label="Adresse e-mail", max_length=254,
        widget=forms.EmailInput(attrs={"autocomplete": "email", "inputmode": "email", "autofocus": True}))
    remember = forms.BooleanField(label="Rester connecté", required=False)
    error_messages = {"invalid_login": "Adresse e-mail ou mot de passe incorrect.",
                      "inactive": "Adresse e-mail ou mot de passe incorrect."}

    def clean_username(self):
        return normalize_email(self.cleaned_data["username"])


class ResetForm(StyledFields, PasswordResetForm):
    def clean_email(self):
        return normalize_email(self.cleaned_data["email"])

    def get_users(self, email):
        # Django exclut par défaut les comptes à mot de passe inutilisable (pensé pour les
        # intégrations SSO). Ici, un mot de passe inutilisable signifie seulement « compte
        # créé par le bureau ou repris du legacy, jamais encore activé » — il doit pouvoir
        # recevoir ce lien, sans quoi il ne devient jamais utilisable.
        from django.contrib.auth import get_user_model
        from django.contrib.auth.forms import _unicode_ci_compare
        email_field_name = get_user_model().get_email_field_name()
        active_users = get_user_model()._default_manager.filter(**{
            "%s__iexact" % email_field_name: email, "is_active": True})
        return (u for u in active_users if _unicode_ci_compare(email, getattr(u, email_field_name)))

    def send_mail(self, subject_template_name, email_template_name, context,
                  from_email, to_email, html_email_template_name=None):
        # Les jetons et le contexte restent ceux de PasswordResetForm Django.
        # Envoi local minimal : pas de queue/outbox, pas de log d'exception SMTP.
        subject = "".join(loader.render_to_string(subject_template_name, context).splitlines())
        message = EmailMultiAlternatives(subject,
            loader.render_to_string(email_template_name, context), from_email, [to_email])
        if html_email_template_name:
            message.attach_alternative(loader.render_to_string(html_email_template_name, context), "text/html")
        try:
            message.send()
        except Exception:
            logger.error("password_reset_delivery_failed")


class NewPasswordForm(StyledFields, SetPasswordForm):
    pass


class ChangePasswordForm(StyledFields, PasswordChangeForm):
    pass


class MfaVerifyForm(StyledFields, forms.Form):
    token = forms.CharField(label="Code de vérification ou code de récupération", max_length=32,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric", "autofocus": True}))


class MfaConfirmForm(StyledFields, forms.Form):
    token = forms.CharField(label="Code affiché par votre application d'authentification", max_length=10,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric"}))


class MfaDisableForm(StyledFields, forms.Form):
    password = forms.CharField(label="Votre mot de passe actuel", widget=forms.PasswordInput)

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise forms.ValidationError("Mot de passe incorrect.")
        return password
