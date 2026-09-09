from django import forms
from apps.accounts.forms import StyledFields


class ScheduleForm(StyledFields, forms.Form):
    tranche1_amount = forms.DecimalField(max_digits=8, decimal_places=2, required=False, min_value=0,
        label="Montant tranche 1 (TND)", help_text="6 premiers mois de l’Année Lions.")
    tranche2_amount = forms.DecimalField(max_digits=8, decimal_places=2, required=False, min_value=0,
        label="Montant tranche 2 (TND)", help_text="6 derniers mois de l’Année Lions.")
