import re
from django import forms
from django.core.validators import validate_email
from apps.accounts.forms import StyledFields
from apps.communications.emailing import safe_subject
from .services import MAX_RECIPIENTS

_SPLIT = re.compile(r"[,;\s]+")


class ComposeForm(StyledFields, forms.Form):
    """Message écrit au nom d'une boîte. Il n'existe volontairement aucun champ « De » :
    l'expéditeur est la boîte de l'URL, dont l'accès est vérifié par le serveur."""
    message_key = forms.UUIDField(widget=forms.HiddenInput)
    to = forms.CharField(label="À", max_length=1000,
        widget=forms.TextInput(attrs={"autocomplete": "off", "inputmode": "email", "placeholder": "adresse@exemple.com"}),
        help_text="Plusieurs adresses possibles, séparées par une virgule.")
    cc = forms.CharField(label="Copie (Cc)", max_length=1000, required=False,
        widget=forms.TextInput(attrs={"autocomplete": "off", "inputmode": "email"}),
        help_text="Facultatif. Les destinataires voient les adresses en copie.")
    subject = forms.CharField(label="Objet", max_length=180)
    body = forms.CharField(label="Message", max_length=20000, widget=forms.Textarea(attrs={"rows": 14}))

    def _addresses(self, name):
        tokens, seen, invalid = [], set(), []
        for token in _SPLIT.split(self.cleaned_data.get(name, "")):
            token = token.strip().strip("<>")
            if not token or token.lower() in seen:
                continue
            seen.add(token.lower())
            try:
                validate_email(token)
            except forms.ValidationError:
                invalid.append(token)
            tokens.append(token)
        if invalid:
            raise forms.ValidationError("Adresse(s) invalide(s) : " + ", ".join(invalid))
        return tokens

    def clean_to(self):
        return self._addresses("to")

    def clean_cc(self):
        return self._addresses("cc")

    def clean_subject(self):
        value = safe_subject(self.cleaned_data["subject"])
        if not value:
            raise forms.ValidationError("L’objet est obligatoire.")
        return value

    def clean_body(self):
        value = self.cleaned_data["body"].replace("\r\n", "\n").replace("\r", "\n").strip()
        if not value:
            raise forms.ValidationError("Le message est obligatoire.")
        return value

    def clean(self):
        cleaned = super().clean()
        if len(cleaned.get("to", [])) + len(cleaned.get("cc", [])) > MAX_RECIPIENTS:
            raise forms.ValidationError(f"{MAX_RECIPIENTS} destinataires maximum par message.")
        return cleaned
