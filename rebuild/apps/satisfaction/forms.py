from django import forms
from apps.accounts.forms import StyledFields

SCALE = [(1, "1 · Très insatisfait"), (2, "2 · Insatisfait"), (3, "3 · Neutre"), (4, "4 · Satisfait"), (5, "5 · Très satisfait")]


class SatisfactionForm(StyledFields, forms.Form):
    score = forms.TypedChoiceField(choices=SCALE, coerce=int, widget=forms.RadioSelect, label="Comment évaluez-vous ce mois au club ?")
    comment = forms.CharField(max_length=1000, required=False, widget=forms.Textarea(attrs={"rows": 4}), label="Votre commentaire (facultatif)")


class PeriodOpenForm(StyledFields, forms.Form):
    year = forms.IntegerField(min_value=2020, max_value=2100, label="Année")
    month = forms.IntegerField(min_value=1, max_value=12, label="Mois")
    auto_schedule = forms.BooleanField(required=False,
        label="Activation automatique (2ᵉ vendredi du mois → 3ᵉ vendredi du mois)",
        help_text="Si coché, les dates ci-dessous sont ignorées : l'heure de référence configurée par l'exploitation est utilisée.")
    opens_at = forms.DateTimeField(required=False, label="Date et heure de lancement",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"))
    closes_at = forms.DateTimeField(required=False, label="Date et heure de fermeture",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"))
    # Obligatoire et sans valeur pré-remplie : le seuil de confidentialité est une décision
    # explicite du responsable à chaque ouverture, jamais un défaut institutionnel silencieux.
    threshold = forms.IntegerField(min_value=1, required=True, label="Effectif minimal avant affichage des résultats (obligatoire)")

    def clean(self):
        data = super().clean()
        if not data.get("auto_schedule"):
            opens_at, closes_at = data.get("opens_at"), data.get("closes_at")
            if not opens_at or not closes_at:
                raise forms.ValidationError("Indiquez la date/heure de lancement et de fermeture, ou activez le mode automatique.")
            if closes_at <= opens_at:
                raise forms.ValidationError("La fermeture doit être postérieure au lancement.")
        return data
