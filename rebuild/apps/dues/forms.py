from django import forms
from apps.accounts.forms import StyledFields
from .models import DuesRecord


class DuesUpdateForm(StyledFields, forms.Form):
    status = forms.ChoiceField(choices=DuesRecord.Status.choices, label="Statut")
    amount = forms.DecimalField(max_digits=8, decimal_places=2, required=False, min_value=0, label="Montant (TND)")
    paid_on = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}), label="Date de règlement")
    motif = forms.CharField(max_length=300, widget=forms.Textarea(attrs={"rows": 2}), label="Motif de la correction")
