from django import forms
from django.core.exceptions import PermissionDenied
from apps.accounts.forms import StyledFields
from apps.core.permissions import can
from .models import AssociationExperience

# Les cases granulaires de partage vers l'annuaire privé (profession, présentation,
# contacts, photo, parcours, mandats) et l'apparition dans l'annuaire ne sont plus
# éditables depuis ce formulaire (recette V1) : elles restent figées à leur valeur
# actuelle, la plus prudente, tant qu'une décision explicite ne les rouvre pas.
VISIBILITY = {
    "directory_visible", "share_profession", "share_bio",
    "share_contacts", "share_photo", "share_experiences", "share_mandates",
}

class ProfileForm(StyledFields, forms.Form):
    first_name = forms.CharField(label="Prénom", max_length=150, widget=forms.TextInput(attrs={"autocomplete":"given-name"}))
    last_name = forms.CharField(label="Nom", max_length=150, widget=forms.TextInput(attrs={"autocomplete":"family-name"}))
    phone = forms.CharField(label="Téléphone", required=False, max_length=32, widget=forms.TextInput(attrs={"autocomplete":"tel", "inputmode":"tel"}))
    profession = forms.CharField(label="Profession", required=False, max_length=150)
    public_title = forms.CharField(label="Titre affiché sur mon profil public", required=False, max_length=150,
        help_text="Par exemple « Past President », « Trésorier », « Président fondateur ». Laissez vide pour afficher « Membre ». "
            "Apparaît uniquement si votre profil public est activé.")
    bio = forms.CharField(label="Présentation", required=False, max_length=1000, widget=forms.Textarea(attrs={"rows":3}))
    photo = forms.FileField(label="Photo privée", required=False, widget=forms.FileInput(attrs={"accept":"image/jpeg,image/png,image/webp"}), help_text="JPEG, PNG ou WebP · 5 Mo · 16 millions de pixels maximum.")
    remove_photo = forms.BooleanField(label="Supprimer ma photo actuelle", required=False)
    public_profile_enabled = forms.BooleanField(label="Rendre mon profil public", required=False,
        help_text="En activant cette option, une page publique Lionsmed sera créée à votre nom. Elle "
            "pourra être consultée sur Internet et apparaître dans les moteurs de recherche. Votre "
            "adresse e-mail et votre numéro de téléphone ne seront jamais affichés.")

    def __init__(self, *args, actor, profile, **kwargs):
        if not can(actor, "profile.edit_own", profile): raise PermissionDenied
        super().__init__(*args, **kwargs)

    def clean(self):
        data = super().clean()
        if data.get("photo") and data.get("remove_photo"):
            raise forms.ValidationError("Choisissez une nouvelle photo ou sa suppression, pas les deux.")
        return data

class ExperienceForm(StyledFields, forms.ModelForm):
    class Meta:
        model = AssociationExperience
        fields = ["network", "club", "function", "district", "start_year", "end_year", "description", "achievements"]
        labels = {"network":"Réseau", "club":"Club", "function":"Poste", "district":"District",
            "start_year":"Année de début", "end_year":"Année de fin",
            "description":"Description", "achievements":"Réalisations"}
        help_texts = {"end_year":"Laisser vide si le poste est toujours actuel."}
        widgets = {"description":forms.Textarea(attrs={"rows":3}), "achievements":forms.Textarea(attrs={"rows":3}),
            "start_year":forms.NumberInput(attrs={"inputmode":"numeric","min":"1917","max":"2100"}),
            "end_year":forms.NumberInput(attrs={"inputmode":"numeric","min":"1917","max":"2100"})}

    def __init__(self, *args, actor, profile, **kwargs):
        instance = kwargs.get("instance")
        if not can(actor, "experience.manage_own", profile) or not can(actor, "experience.manage_own", instance or profile): raise PermissionDenied
        super().__init__(*args, **kwargs)
        self.instance.profile = profile
