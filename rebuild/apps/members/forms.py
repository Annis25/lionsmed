from django import forms
from django.core.exceptions import PermissionDenied
from apps.accounts.forms import StyledFields
from apps.core.permissions import can
from .models import AssociationExperience

VISIBILITY = {
    "directory_visible": "Apparaître dans l’annuaire (nom et rôle)",
    "share_profession": "Partager ma profession", "share_bio": "Partager ma présentation",
    "share_contacts": "Partager mon email et mon téléphone", "share_photo": "Partager ma photo",
    "share_experiences": "Partager mon parcours Lions / LEO", "share_mandates": "Partager mes mandats validés",
}

class ProfileForm(StyledFields, forms.Form):
    first_name = forms.CharField(label="Prénom", max_length=150, widget=forms.TextInput(attrs={"autocomplete":"given-name"}))
    last_name = forms.CharField(label="Nom", max_length=150, widget=forms.TextInput(attrs={"autocomplete":"family-name"}))
    phone = forms.CharField(label="Téléphone", required=False, max_length=32, widget=forms.TextInput(attrs={"autocomplete":"tel", "inputmode":"tel"}))
    profession = forms.CharField(label="Profession", required=False, max_length=150)
    bio = forms.CharField(label="Présentation", required=False, max_length=1000, widget=forms.Textarea(attrs={"rows":3}))
    photo = forms.FileField(label="Photo privée", required=False, widget=forms.FileInput(attrs={"accept":"image/jpeg,image/png,image/webp"}), help_text="JPEG, PNG ou WebP · 5 Mo · 16 millions de pixels maximum.")
    remove_photo = forms.BooleanField(label="Supprimer ma photo actuelle", required=False)
    for key, label in VISIBILITY.items():
        locals()[key] = forms.BooleanField(label=label, required=False)
    del key, label

    def __init__(self, *args, actor, profile, **kwargs):
        if not can(actor, "profile.edit_own", profile): raise PermissionDenied
        super().__init__(*args, **kwargs)

    def clean(self):
        data = super().clean()
        if data.get("photo") and data.get("remove_photo"):
            raise forms.ValidationError("Choisissez une nouvelle photo ou sa suppression, pas les deux.")
        return data

class ExperienceForm(StyledFields, forms.ModelForm):
    starts_on = forms.DateField(label="Mois de début", input_formats=["%Y-%m"], widget=forms.DateInput(format="%Y-%m", attrs={"type":"month"}))
    ends_on = forms.DateField(label="Mois de fin", required=False, input_formats=["%Y-%m"], widget=forms.DateInput(format="%Y-%m", attrs={"type":"month"}))
    class Meta:
        model = AssociationExperience
        fields = ["network", "club", "function", "district", "starts_on", "ends_on", "description", "achievements"]
        labels = {"network":"Réseau", "club":"Club", "function":"Fonction", "district":"District", "description":"Description", "achievements":"Réalisations"}
        widgets = {"description":forms.Textarea(attrs={"rows":3}), "achievements":forms.Textarea(attrs={"rows":3})}

    def __init__(self, *args, actor, profile, **kwargs):
        instance = kwargs.get("instance")
        if not can(actor, "experience.manage_own", profile) or not can(actor, "experience.manage_own", instance or profile): raise PermissionDenied
        super().__init__(*args, **kwargs)
        self.instance.profile = profile
