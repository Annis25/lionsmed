from django import forms
from apps.accounts.forms import StyledFields
from apps.core.models import PublicImage
from .models import Vote, VoteOption


class VoteForm(StyledFields, forms.ModelForm):
    creation_key = forms.UUIDField(widget=forms.HiddenInput)
    class Meta:
        model = Vote
        fields = ["title", "description", "mode", "blank_allowed", "disclosure"]
        labels = {"title": "Titre", "description": "Description", "mode": "Type de scrutin",
            "blank_allowed": "Vote blanc autorisé", "disclosure": "Secret du vote"}
        help_texts = {"disclosure": "Vote secret : personne, pas même l’administrateur du site, ne peut savoir qui a voté quoi. "
            "Vote nominatif : l’administrateur du site pourra voir le choix de chaque électeur après la clôture ; "
            "les électeurs en sont avertis avant de voter. Ce choix ne peut plus être modifié après la création."}
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Un envoi sans ce champ (formulaire ouvert avant la mise à jour) reste un vote secret.
        self.fields["disclosure"].required = False

    def clean_disclosure(self):
        return self.cleaned_data.get("disclosure") or Vote.Disclosure.SECRET


class VoteOptionForm(StyledFields, forms.Form):
    label = forms.CharField(max_length=180, label="Libellé ou nom du candidat")
    presentation = forms.CharField(max_length=2000, required=False, widget=forms.Textarea(attrs={"rows": 3}), label="Présentation (facultatif)")
    photo = forms.ModelChoiceField(queryset=PublicImage.objects.filter(approved_at__isnull=False), required=False, label="Photo autorisée (facultatif)")
