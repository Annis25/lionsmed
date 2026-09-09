from django import forms
from apps.accounts.forms import StyledFields
from apps.core.models import PublicImage
from .models import Vote, VoteOption


class VoteForm(StyledFields, forms.ModelForm):
    class Meta:
        model = Vote
        fields = ["title", "description", "mode", "opens_at", "closes_at", "min_choices", "max_choices", "blank_allowed"]
        labels = {"title": "Titre", "description": "Description", "mode": "Type de scrutin",
            "opens_at": "Ouverture — heure de Tunis", "closes_at": "Clôture — heure de Tunis",
            "min_choices": "Nombre minimal de choix", "max_choices": "Nombre maximal de choix",
            "blank_allowed": "Vote blanc autorisé"}
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "opens_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "closes_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def clean(self):
        data = super().clean()
        opens_at, closes_at = data.get("opens_at"), data.get("closes_at")
        if opens_at and closes_at and closes_at <= opens_at:
            raise forms.ValidationError("La clôture doit être postérieure à l'ouverture.")
        min_choices, max_choices = data.get("min_choices"), data.get("max_choices")
        if min_choices and max_choices and max_choices < min_choices:
            raise forms.ValidationError("Le nombre maximal de choix doit être au moins égal au minimum.")
        return data


class VoteOptionForm(StyledFields, forms.Form):
    label = forms.CharField(max_length=180, label="Libellé ou nom du candidat")
    presentation = forms.CharField(max_length=2000, required=False, widget=forms.Textarea(attrs={"rows": 3}), label="Présentation (facultatif)")
    photo = forms.ModelChoiceField(queryset=PublicImage.objects.filter(approved_at__isnull=False), required=False, label="Photo autorisée (facultatif)")
