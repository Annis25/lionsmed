import re
from django import forms
from apps.core.phone import PhoneField
from django.core.validators import validate_email
from django.utils.html import strip_tags
from django.core import signing
import uuid
from apps.accounts.forms import StyledFields
from apps.accounts.models import normalize_email
from apps.members.models import MembershipApplication
from .models import ContactRequest
from .services import INELIGIBLE_EXTERNAL_MESSAGE, ineligible_known_addresses

EXTRA_EMAILS_MAX = 50
_EMAIL_SPLIT_RE = re.compile(r"[,;\s]+")

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
    phone = PhoneField(required=True)
    kind="application"
    consent=forms.BooleanField(label="J’accepte l’utilisation de ces informations pour traiter ma candidature.")
    origin=forms.ChoiceField(label="Comment avez-vous connu le club ?",required=False,choices=[("","Sélectionner…"),("MEMBRE","Par un membre"),("ACTION","Lors d’une action"),("SOCIAL","Réseaux sociaux"),("PRESSE","Presse"),("LIONS","Site de Lions International"),("AUTRE","Autre")])
    class Meta:
        model=MembershipApplication
        fields=["last_name","first_name","email","phone","profession","motivation","origin"]
        labels={"last_name":"Nom","first_name":"Prénom","email":"Adresse e-mail","phone":"Téléphone","profession":"Profession","motivation":"Pourquoi souhaitez-vous nous rejoindre ?"}
        widgets={"last_name":forms.TextInput(attrs={"autocomplete":"family-name"}),"first_name":forms.TextInput(attrs={"autocomplete":"given-name"}),"email":forms.EmailInput(attrs={"autocomplete":"email","inputmode":"email"}),"phone":forms.TextInput(attrs={"autocomplete":"tel","inputmode":"tel"}),"motivation":forms.Textarea(attrs={"rows":6})}
class ContactForm(SubmissionForm):
    phone = PhoneField(required=False)
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
    """Destinataires = membres cochés + adresses externes, deux listes indépendantes.

    `eligible` (services.eligible_broadcast_members) fixe les seuls identifiants de
    membres acceptés : un identifiant fabriqué, ou celui d'un compte devenu inéligible,
    est rejeté ici avant même d'atteindre le service. `require_recipients` n'est vrai que
    pour vérifier ou envoyer : un aperçu ou un test ne demandent aucun destinataire."""
    campaign_key = forms.UUIDField(widget=forms.HiddenInput, required=True)
    subject = forms.CharField(max_length=180, label="Objet")
    body = forms.CharField(max_length=8000, label="Message", widget=forms.Textarea(attrs={"rows": 12}))
    members = forms.MultipleChoiceField(required=False, label="Membres du club", widget=forms.CheckboxSelectMultiple,
        error_messages={"invalid_choice": "Un membre sélectionné n’est plus disponible pour la communication. Vérifiez la sélection.",
                        "invalid_list": "Sélection de membres invalide."})
    extra_emails = forms.CharField(required=False, label="Adresses externes",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "adresse@exemple.com"}),
        help_text="Une adresse par ligne, ou séparées par une virgule.")
    # Présent seulement pour qui tient plusieurs boîtes institutionnelles : les choix sont
    # les siennes, fixées par le serveur. Une seule boîte (ou aucune) : rien à choisir.
    sender_mailbox = forms.ChoiceField(label="Envoyer depuis",
        error_messages={"invalid_choice": "Cette adresse d’envoi ne vous est pas attribuée."})

    def __init__(self, *args, eligible=(), require_recipients=False, senders=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.require_recipients = require_recipients
        self.eligible = list(eligible)
        if len(senders) > 1:
            self.fields["sender_mailbox"].choices = [(mailbox.key, mailbox.address) for mailbox in senders]
            self.fields["sender_mailbox"].initial = senders[0].key
        else:
            del self.fields["sender_mailbox"]
        self.fields["members"].choices = [(str(user.pk), user.get_full_name() or user.email) for user, _ in self.eligible]
        self.extra_emails_submitted = 0

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

    def clean_extra_emails(self):
        raw = self.cleaned_data.get("extra_emails", "")
        tokens = [token.strip() for token in _EMAIL_SPLIT_RE.split(raw) if token.strip()]
        # Nombre d'adresses réellement saisies : sert à annoncer les doublons ignorés.
        self.extra_emails_submitted = len(tokens)
        deduped, seen = [], set()
        for token in tokens:
            key = token.lower()
            if key not in seen:
                seen.add(key)
                deduped.append(token)
        invalid = []
        for token in deduped:
            try:
                validate_email(token)
            except forms.ValidationError:
                invalid.append(token)
        if invalid:
            raise forms.ValidationError("Adresse(s) invalide(s) : " + ", ".join(invalid))
        if len(deduped) > EXTRA_EMAILS_MAX:
            raise forms.ValidationError(f"{EXTRA_EMAILS_MAX} adresses externes maximum ({len(deduped)} saisies).")
        blocked = ineligible_known_addresses(deduped, self.eligible)
        if blocked:
            raise forms.ValidationError(INELIGIBLE_EXTERNAL_MESSAGE % ", ".join(blocked))
        return deduped

    def clean(self):
        cleaned = super().clean()
        # Seulement si les deux listes sont elles-mêmes valides : une adresse mal saisie
        # porte déjà sa propre erreur, inutile d'y ajouter « aucun destinataire ».
        if (self.require_recipients and "members" in cleaned and "extra_emails" in cleaned
                and not cleaned["members"] and not cleaned["extra_emails"]):
            raise forms.ValidationError("Sélectionnez au moins un membre ou ajoutez une adresse externe.")
        return cleaned
