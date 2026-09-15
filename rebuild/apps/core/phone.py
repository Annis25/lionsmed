import re
from django import forms
from django.core.exceptions import ValidationError


def normalize_phone(value):
    """Saisie tunisienne nationale ou E.164 international ; aucune conversion des données historiques."""
    value = (value or "").strip()
    if not value:
        return ""
    if not re.fullmatch(r"\+?[0-9 ]+", value):
        raise ValidationError("Téléphone : chiffres uniquement, sans lettres.")
    number = value.replace(" ", "")
    if number.startswith("+216"):
        national = number[4:]
    elif not number.startswith("+"):
        national = number
    else:
        if not re.fullmatch(r"\+[1-9][0-9]{7,14}", number):
            raise ValidationError("Numéro international invalide (8 à 15 chiffres).")
        return number
    if not re.fullmatch(r"[2-9][0-9]{7}", national):
        raise ValidationError("Tunisie (+216) : indiquez un numéro de 8 chiffres valide.")
    return "+216" + national


class PhoneWidget(forms.TextInput):
    input_type = "tel"
    template_name = "components/forms/phone_input.html"


class PhoneField(forms.CharField):
    def __init__(self, **kwargs):
        kwargs.setdefault("label", "Téléphone — Tunisie (+216) par défaut")
        kwargs.setdefault("help_text", "8 chiffres en Tunisie. Pour un autre pays, indiquez + et son indicatif.")
        kwargs.setdefault("widget", PhoneWidget(attrs={"type": "tel", "inputmode": "numeric", "autocomplete": "tel", "pattern": r"\+?[0-9 ]+", "placeholder": "20 123 456", "data-phone": ""}))
        super().__init__(**kwargs)

    def to_python(self, value):
        return normalize_phone(super().to_python(value))
