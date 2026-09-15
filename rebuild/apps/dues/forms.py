from django import forms
from apps.accounts.forms import StyledFields


class ScheduleForm(StyledFields, forms.Form):
    tranche1_amount = forms.DecimalField(max_digits=8, decimal_places=2, required=False, min_value=0,
        label="Montant tranche 1 (TND)", help_text="6 premiers mois de l’Année Lions.")
    tranche2_amount = forms.DecimalField(max_digits=8, decimal_places=2, required=False, min_value=0,
        label="Montant tranche 2 (TND)", help_text="6 derniers mois de l’Année Lions.")
class TranchePaymentForm(forms.Form):
    paid = forms.TypedChoiceField(choices=[("1", "Payée"), ("0", "Non payée")], coerce=lambda value: value == "1")
    paid_on = forms.DateField(required=False)
    motif = forms.CharField(max_length=300, required=False)
