from django import forms
from apps.accounts.forms import StyledFields

SCALE = [(1, "1 · Très insatisfait"), (2, "2 · Insatisfait"), (3, "3 · Neutre"), (4, "4 · Satisfait"), (5, "5 · Très satisfait")]


class SatisfactionForm(StyledFields, forms.Form):
    score = forms.TypedChoiceField(choices=SCALE, coerce=int, widget=forms.RadioSelect, label="Comment évaluez-vous ce mois au club ?")
    comment = forms.CharField(max_length=1000, required=False, widget=forms.Textarea(attrs={"rows": 4}), label="Votre commentaire (facultatif)")


class PeriodOpenForm(StyledFields, forms.Form):
    year = forms.IntegerField(min_value=2020, max_value=2100, label="Année")
    month = forms.IntegerField(min_value=1, max_value=12, label="Mois")
    # Obligatoire et sans valeur pré-remplie : le seuil de confidentialité est une décision
    # explicite du responsable à chaque ouverture, jamais un défaut institutionnel silencieux.
    threshold = forms.IntegerField(min_value=1, required=True, label="Effectif minimal avant affichage des résultats (obligatoire)")
