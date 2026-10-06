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


class MandateForm(StyledFields, forms.Form):
    """Saisie d'un mandat. La fonction se choisit dans le catalogue du bureau
    (apps.governance.functions) ; « Autre fonction » reste possible pour les responsabilités
    hors bureau, mais une variante d'une fonction du catalogue y est refusée (service)."""
    OTHER = "__autre__"
    profile = forms.ModelChoiceField(label="Membre", queryset=MemberProfile.objects.none(), empty_label="Sélectionner…")
    function_choice = forms.ChoiceField(label="Fonction")
    function_other = forms.CharField(label="Autre fonction", required=False, max_length=150,
        help_text="Uniquement si la fonction ne figure pas dans la liste (ex. responsable d’une commission).")
    lions_year = forms.ModelChoiceField(label="Année Lions", queryset=None, empty_label=None)
    starts_on = forms.DateField(label="Premier jour", required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        help_text="Laisser vide : début de l’Année Lions.")
    last_day = forms.DateField(label="Dernier jour", required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        help_text="Laisser vide : fin de l’Année Lions.")
    validated = forms.BooleanField(label="Mandat validé par le club", required=False)
    public_authorized = forms.BooleanField(label="Afficher dans « Notre bureau » sur le site public", required=False,
        help_text="Uniquement avec l’accord de la personne. Sa photo n’apparaît que si elle a elle-même activé son profil public.")

    def __init__(self, *args, mandate=None, default_year=None, default_profile_id=None, **kwargs):
        from datetime import timedelta
        from .functions import canonical_label, selectable_labels
        from .models import LionsYear
        from .selectors import mandate_candidates
        initial = kwargs.setdefault("initial", {})
        if mandate:
            label = canonical_label(mandate.function)
            initial.update(profile=mandate.profile_id, lions_year=mandate.lions_year_id,
                function_choice=label or self.OTHER, function_other="" if label else mandate.function,
                starts_on=mandate.starts_on, last_day=mandate.ends_on - timedelta(days=1),
                validated=bool(mandate.validated_at), public_authorized=mandate.public_authorized)
        else:
            initial.setdefault("validated", True)
            if default_year: initial.setdefault("lions_year", default_year.pk)
            if default_profile_id: initial.setdefault("profile", default_profile_id)
        super().__init__(*args, **kwargs)
        self.fields["profile"].queryset = mandate_candidates(include=mandate.profile_id if mandate else None)
        self.fields["profile"].label_from_instance = lambda p: f"{p.user.last_name} {p.user.first_name}".strip() or p.user.email
        self.fields["function_choice"].choices = [("", "Sélectionner…"),
            ("Fonctions du bureau", [(label, label) for label in selectable_labels()]),
            (self.OTHER, "Autre fonction…")]
        self.fields["lions_year"].queryset = LionsYear.objects.all()

    def clean(self):
        from datetime import timedelta
        from django.core.exceptions import ValidationError
        from .functions import validate_function
        data = super().clean()
        choice = data.get("function_choice")
        if choice == self.OTHER:
            if not data.get("function_other", "").strip():
                self.add_error("function_other", "Précisez la fonction.")
            else:
                try: data["function"] = validate_function(data["function_other"])
                except ValidationError as error: self.add_error("function_other", error)
        elif choice:
            data["function"] = choice
        year = data.get("lions_year")
        if year:
            starts_on = data.get("starts_on") or year.starts_on
            ends_on = data["last_day"] + timedelta(days=1) if data.get("last_day") else year.ends_on
            if not year.starts_on <= starts_on < ends_on <= year.ends_on:
                raise ValidationError(f"Les dates doivent être comprises dans l’Année Lions {year.label} "
                    f"(du {year.starts_on:%d/%m/%Y} au {year.ends_on - timedelta(days=1):%d/%m/%Y}), dans l’ordre.")
            data["starts_on"], data["ends_on"] = starts_on, ends_on
        return data

    def mandate_data(self):
        data = self.cleaned_data
        return {key: data[key] for key in ["profile", "function", "lions_year", "starts_on", "ends_on", "validated", "public_authorized"]}
