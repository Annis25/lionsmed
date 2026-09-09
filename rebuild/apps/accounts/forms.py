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
