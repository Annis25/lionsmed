from django import forms
from apps.accounts.forms import StyledFields
from .models import Document


class DocumentForm(StyledFields, forms.Form):
    title = forms.CharField(max_length=180, label="Titre")
    description = forms.CharField(max_length=2000, required=False, widget=forms.Textarea(attrs={"rows": 3}), label="Description")
    category = forms.ChoiceField(choices=Document.Category.choices, label="Catégorie")
    visibility = forms.ChoiceField(choices=Document.Visibility.choices, label="Visibilité")
    file = forms.FileField(label="Fichier", help_text="PDF, DOCX, XLSX, PNG ou JPEG · 50 Mo maximum.")


class DocumentGrantForm(StyledFields, forms.Form):
    email = forms.EmailField(label="Adresse email du compte autorisé")
    expires_at = forms.DateTimeField(required=False, label="Expiration (optionnelle)",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"), input_formats=["%Y-%m-%dT%H:%M"])
