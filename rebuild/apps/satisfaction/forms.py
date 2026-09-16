from django import forms
from apps.accounts.forms import StyledFields

SCALE = [(1, "1 · Très insatisfait"), (2, "2 · Insatisfait"), (3, "3 · Neutre"), (4, "4 · Satisfait"), (5, "5 · Très satisfait")]


class SatisfactionForm(StyledFields, forms.Form):
    score = forms.TypedChoiceField(choices=SCALE, coerce=int, widget=forms.RadioSelect, label="Comment évaluez-vous ce mois au club ?")
    comment = forms.CharField(max_length=500, required=False, widget=forms.Textarea(attrs={"rows": 4, "maxlength": 500}),
        label="Un commentaire ? (optionnel)")

    def __init__(self, *args, period=None, **kwargs):
        super().__init__(*args, **kwargs)
        if period:
            for axis in period.axes.all():
                self.fields[f"axis_{axis.pk}"] = forms.TypedChoiceField(choices=SCALE, coerce=int, label=axis.label, widget=forms.RadioSelect)
        # « comment » ré-inséré en dernier : le template numérote les questions par
        # position dans le formulaire (score=1, puis les axes) et affiche le commentaire
        # séparément après la boucle — son rang dans self.fields ne doit jamais compter.
        self.fields["comment"] = self.fields.pop("comment")


class PeriodForm(StyledFields, forms.Form):
    title = forms.CharField(max_length=180, required=False, label="Titre")
    description = forms.CharField(max_length=3000, required=False, label="Description", widget=forms.Textarea(attrs={"rows": 3}))
    opens_at = forms.DateTimeField(label="Date et heure de lancement",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"))
    closes_at = forms.DateTimeField(label="Date et heure de fermeture",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"))
    # Obligatoire et sans valeur pré-remplie : le seuil de confidentialité est une décision
    # explicite du responsable à chaque ouverture, jamais un défaut institutionnel silencieux.
    threshold = forms.IntegerField(min_value=1, required=True, label="Effectif minimal avant affichage des résultats")

    def __init__(self, *args, include_axes=False, **kwargs):
        super().__init__(*args, **kwargs)
        if include_axes:
            self.fields["axes"] = forms.CharField(
                label="Axes de satisfaction",
                help_text="Ajoutez au moins un axe. Leur ordre sera celui affiché aux membres.",
                widget=forms.Textarea(attrs={"rows": 5, "data-axis-source": "", "class": "champ__input"}),
            )

    def clean(self):
        data = super().clean()
        opens_at, closes_at = data.get("opens_at"), data.get("closes_at")
        if opens_at and closes_at and closes_at <= opens_at:
            raise forms.ValidationError("La fermeture doit être postérieure au lancement.")
        if "axes" in self.fields and data.get("axes"):
            labels = [label.strip() for label in data["axes"].splitlines() if label.strip()]
            if not labels:
                self.add_error("axes", "Ajoutez au moins un axe.")
            elif len(labels) > 30:
                self.add_error("axes", "30 axes maximum.")
            elif any(len(label) > 180 for label in labels):
                self.add_error("axes", "Chaque axe doit contenir au maximum 180 caractères.")
            elif len({label.casefold() for label in labels}) != len(labels):
                self.add_error("axes", "Chaque axe doit avoir un nom différent.")
            else:
                data["axes"] = labels
        return data


class AxisForm(StyledFields, forms.Form):
    label = forms.CharField(max_length=180, label="Nom de l’axe")
