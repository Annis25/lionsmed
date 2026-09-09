from django import forms
from django.utils.html import strip_tags
from django.core import signing
import uuid
from apps.accounts.forms import StyledFields
from apps.accounts.models import normalize_email
from apps.members.models import MembershipApplication
from .models import ContactRequest

class SubmissionForm(StyledFields,forms.ModelForm):
    submission_token=forms.CharField(widget=forms.HiddenInput)
    website=forms.CharField(required=False,label="Laisser ce champ vide",widget=forms.TextInput(attrs={"tabindex":"-1","autocomplete":"off"}))
    def clean_email(self):return normalize_email(self.cleaned_data["email"])
    def clean_submission_token(self):
        try:
            value=signing.loads(self.cleaned_data["submission_token"],salt="public-submission",max_age=3600)
            if value["kind"]!=self.kind:raise ValueError
            from uuid import UUID
            return UUID(value["id"])
        except (signing.BadSignature,KeyError,ValueError):raise forms.ValidationError("Formulaire expiré. Rechargez la page avant de réessayer.")
    def clean_website(self):
        if self.cleaned_data["website"]:raise forms.ValidationError("Cette soumission ne peut pas être traitée.")
        return ""

class ApplicationForm(SubmissionForm):
    kind="application"
    consent=forms.BooleanField(label="J’accepte l’utilisation de ces informations pour traiter ma candidature.")
    origin=forms.ChoiceField(label="Comment avez-vous connu le club ?",required=False,choices=[("","Sélectionner…"),("MEMBRE","Par un membre"),("ACTION","Lors d’une action"),("SOCIAL","Réseaux sociaux"),("PRESSE","Presse"),("LIONS","Site de Lions International"),("AUTRE","Autre")])
    class Meta:
        model=MembershipApplication
        fields=["last_name","first_name","email","phone","profession","motivation","origin"]
        labels={"last_name":"Nom","first_name":"Prénom","email":"Adresse e-mail","phone":"Téléphone","profession":"Profession","motivation":"Pourquoi souhaitez-vous nous rejoindre ?"}
        widgets={"last_name":forms.TextInput(attrs={"autocomplete":"family-name"}),"first_name":forms.TextInput(attrs={"autocomplete":"given-name"}),"email":forms.EmailInput(attrs={"autocomplete":"email","inputmode":"email"}),"phone":forms.TextInput(attrs={"autocomplete":"tel","inputmode":"tel"}),"motivation":forms.Textarea(attrs={"rows":6})}
class ContactForm(SubmissionForm):
    kind="contact"
    class Meta:
        model=ContactRequest
        fields=["name","email","phone","subject","message"]
        labels={"name":"Votre nom","email":"Adresse e-mail","phone":"Téléphone","subject":"Objet de votre message","message":"Votre message"}
        widgets={"name":forms.TextInput(attrs={"autocomplete":"name"}),"email":forms.EmailInput(attrs={"autocomplete":"email","inputmode":"email"}),"phone":forms.TextInput(attrs={"autocomplete":"tel","inputmode":"tel"}),"message":forms.Textarea(attrs={"rows":6})}

class ImportantNotificationForm(StyledFields,forms.Form):
    email=forms.EmailField(label="Adresse email du destinataire")
    title=forms.CharField(max_length=180,label="Titre")
    excerpt=forms.CharField(max_length=300,widget=forms.Textarea(attrs={"rows":3}),label="Extrait",required=False)


class MemberBroadcastForm(StyledFields, forms.Form):
    campaign_key = forms.UUIDField(widget=forms.HiddenInput, required=True)
    subject = forms.CharField(max_length=180, label="Objet")
    body = forms.CharField(max_length=8000, label="Message", widget=forms.Textarea(attrs={"rows": 12}))

    def clean_subject(self):
        value = " ".join(strip_tags(self.cleaned_data["subject"]).replace("\r", "").replace("\n", " ").split())
        if not value:
            raise forms.ValidationError("L’objet est obligatoire.")
        return value

    def clean_body(self):
        # Le Bureau écrit du texte, jamais du HTML : cela bloque XSS, attributs d'événement
        # et protocoles dangereux sans faire reposer la sécurité sur le navigateur.
        raw = self.cleaned_data["body"].replace("\r\n", "\n").replace("\r", "\n")
        value = strip_tags(raw).strip()
        if not value:
            raise forms.ValidationError("Le message est obligatoire.")
        return value
