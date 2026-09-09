from django import forms
from django.core.exceptions import PermissionDenied
from apps.accounts.forms import StyledFields
from apps.core.permissions import can
from apps.core.models import PublicImage
from .models import Event


class QuickEventForm(StyledFields, forms.Form):
    """Ajout rapide depuis le calendrier interne — volontairement minimal (titre,
    description, dates, lieu, lien) : la fiche éditoriale complète (SEO, image, mise en
    avant publique) reste dans /espace/contenu/, pas dans ce formulaire."""
    title = forms.CharField(max_length=180, label="Titre")
    description = forms.CharField(max_length=5000, required=False, widget=forms.Textarea(attrs={"rows": 3}), label="Description")
    all_day = forms.BooleanField(required=False, label="Journée entière")
    starts_at = forms.DateTimeField(label="Début", widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"))
    ends_at = forms.DateTimeField(required=False, label="Fin", widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"))
    location = forms.CharField(max_length=200, required=False, label="Lieu")
    meeting_link = forms.URLField(max_length=300, required=False, label="Lien de réunion (facultatif)")
class EventForm(StyledFields, forms.ModelForm):
    class Meta:
        model=Event
        fields=["title","slug","summary","body","meta_title","meta_description","cover","social_image"]+["starts_at","ends_at","location","category","visibility","capacity","registration_enabled"]
        labels={"title":"Titre","slug":"Slug stable","summary":"Résumé","body":"Récit / description","cover":"Image de couverture autorisée","social_image":"Image sociale autorisée","meta_title":"Titre SEO","meta_description":"Description SEO","performed_on":"Date de réalisation","location":"Lieu","city":"Ville","country":"Pays","axis":"Axe","beneficiaries":"Bénéficiaires (si validés)","partners":"Partenaires validés","evidence":"Source du bilan","author_name":"Signature publique validée","starts_at":"Début — heure de Tunis","ends_at":"Fin — heure de Tunis","category":"Catégorie","visibility":"Visibilité","capacity":"Capacité (laisser vide si illimitée)","registration_enabled":"Ouvrir les inscriptions (RSVP) des membres"}
        widgets={"performed_on":forms.DateInput(attrs={"type":"date"},format="%Y-%m-%d"),"starts_at":forms.DateTimeInput(attrs={"type":"datetime-local"},format="%Y-%m-%dT%H:%M"),"ends_at":forms.DateTimeInput(attrs={"type":"datetime-local"},format="%Y-%m-%dT%H:%M"),"body":forms.Textarea(attrs={"rows":6}),"summary":forms.Textarea(attrs={"rows":3})}
    def __init__(self,*args,actor,**kwargs):
        instance=kwargs.get("instance")
        if not can(actor,"event.edit" if instance else "event.create",instance):raise PermissionDenied
        super().__init__(*args,**kwargs)
        self.fields["slug"].required=False
        for name in ["cover","social_image"]:self.fields[name].queryset=PublicImage.objects.filter(approved_at__isnull=False)
