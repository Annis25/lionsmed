from django import forms
from django.utils.text import slugify

from .models import Event


INPUT_CLASS = (
    'w-full px-4 py-2.5 text-sm bg-gray-50 border border-gray-200 rounded-lg outline-none '
    'focus:ring-2 focus:ring-navy-500/20 focus:border-navy-400 transition-all'
)
CHECKBOX_CLASS = 'w-4 h-4 rounded border-gray-300 text-navy-600 focus:ring-navy-500/20'


class EventForm(forms.ModelForm):
    """Création / édition d'un événement depuis le panel admin."""

    class Meta:
        model = Event
        fields = [
            'title', 'description', 'event_type',
            'date_start', 'date_end', 'location',
            'image', 'price', 'capacity',
            'is_public', 'is_payant', 'is_featured',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': "Titre de l'événement"}),
            'description': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 6}),
            'event_type': forms.Select(attrs={'class': INPUT_CLASS}),
            'date_start': forms.DateTimeInput(attrs={'class': INPUT_CLASS, 'type': 'datetime-local'}),
            'date_end': forms.DateTimeInput(attrs={'class': INPUT_CLASS, 'type': 'datetime-local'}),
            'location': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Sfax — lieu précis'}),
            'image': forms.ClearableFileInput(attrs={'class': 'text-sm text-gray-600'}),
            'price': forms.NumberInput(attrs={'class': INPUT_CLASS, 'step': '0.01', 'min': '0'}),
            'capacity': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': '0'}),
            'is_public': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS}),
            'is_payant': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS}),
            'is_featured': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS}),
        }
        labels = {
            'title': 'Titre',
            'description': 'Description',
            'event_type': "Type d'événement",
            'date_start': 'Date de début',
            'date_end': 'Date de fin',
            'location': 'Lieu',
            'image': 'Image',
            'price': 'Prix (TND)',
            'capacity': 'Capacité',
            'is_public': 'Visible sur le site public',
            'is_payant': 'Événement payant',
            'is_featured': 'Mettre en avant',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # date_end et capacity sont facultatifs sur le modèle : on le reflète ici.
        self.fields['date_end'].required = False
        self.fields['capacity'].required = False

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get('date_start'), cleaned.get('date_end')
        if start and end and end < start:
            self.add_error('date_end', 'La date de fin doit suivre la date de début.')
        if cleaned.get('is_payant') and not cleaned.get('price'):
            self.add_error('price', 'Indiquez un prix pour un événement payant.')
        return cleaned

    def save(self, commit=True):
        event = super().save(commit=False)
        if not event.slug:
            event.slug = self._unique_slug(event.title)
        if commit:
            event.save()
        return event

    def _unique_slug(self, title):
        base = slugify(title) or 'evenement'
        slug, counter = base, 2
        while Event.objects.filter(slug=slug).exclude(pk=self.instance.pk).exists():
            slug = f'{base}-{counter}'
            counter += 1
        return slug
