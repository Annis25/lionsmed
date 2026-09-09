from django import forms
from apps.accounts.forms import StyledFields
from apps.accounts.models import normalize_email
from apps.members.models import MemberProfile
from .models import Role

# SUPER_ADMIN reste hors de portée de cette page : sa création et sa modification passent
# uniquement par la procédure technique (createsuperuser / grant_role en CLI).
ASSIGNABLE_ROLES = [choice for choice in Role.choices if choice[0] != Role.SUPER_ADMIN]


class MemberCreateForm(StyledFields, forms.Form):
    first_name = forms.CharField(label="Prénom", max_length=150, widget=forms.TextInput(attrs={"autocomplete": "given-name"}))
    last_name = forms.CharField(label="Nom", max_length=150, widget=forms.TextInput(attrs={"autocomplete": "family-name"}))
    email = forms.EmailField(label="Adresse e-mail", widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    role = forms.ChoiceField(label="Rôle", choices=ASSIGNABLE_ROLES)

    def clean_email(self):
        from django.contrib.auth import get_user_model
        email = normalize_email(self.cleaned_data["email"])
        if get_user_model().objects.filter(email=email).exists():
            raise forms.ValidationError("Cette adresse e-mail est déjà associée à un compte.")
        return email


class RoleChangeForm(StyledFields, forms.Form):
    role = forms.ChoiceField(label="Rôle", choices=ASSIGNABLE_ROLES)


class StatusChangeForm(StyledFields, forms.Form):
    status = forms.ChoiceField(label="Statut", choices=MemberProfile.Status.choices)


class EmailChangeForm(StyledFields, forms.Form):
    email = forms.EmailField(label="Adresse e-mail")

    def clean_email(self):
        return normalize_email(self.cleaned_data["email"])


class LionsYearForm(StyledFields, forms.Form):
    start_year = forms.IntegerField(label="Année de début (juillet)", min_value=2000, max_value=2100,
        help_text="L’Année Lions ainsi créée ira du 1er juillet de cette année au 1er juillet de l’année suivante.")
