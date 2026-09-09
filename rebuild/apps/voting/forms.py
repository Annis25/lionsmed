from django import forms
from apps.accounts.forms import StyledFields
from apps.core.models import PublicImage
from .models import Vote, VoteOption


class VoteForm(StyledFields, forms.ModelForm):
    class Meta:
        model = Vote
        fields = ["title", "description", "mode", "blank_allowed"]
        labels = {"title": "Titre", "description": "Description", "mode": "Type de scrutin",
            "blank_allowed": "Vote blanc autorisé"}
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}


class VoteOptionForm(StyledFields, forms.Form):
    label = forms.CharField(max_length=180, label="Libellé ou nom du candidat")
    presentation = forms.CharField(max_length=2000, required=False, widget=forms.Textarea(attrs={"rows": 3}), label="Présentation (facultatif)")
    photo = forms.ModelChoiceField(queryset=PublicImage.objects.filter(approved_at__isnull=False), required=False, label="Photo autorisée (facultatif)")
