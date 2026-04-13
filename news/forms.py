from django import forms
from django.utils import timezone
from django.utils.text import slugify

from .models import Article


INPUT_CLASS = (
    'w-full px-4 py-2.5 text-sm bg-gray-50 border border-gray-200 rounded-lg outline-none '
    'focus:ring-2 focus:ring-navy-500/20 focus:border-navy-400 transition-all'
)


class ArticleForm(forms.ModelForm):
    """Création / édition d'un article depuis le panel admin."""

    class Meta:
        model = Article
        fields = [
            'title', 'excerpt', 'content',
            'category', 'image', 'status', 'reading_time',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': "Titre de l'article"}),
            'excerpt': forms.Textarea(attrs={
                'class': INPUT_CLASS, 'rows': 3,
                'placeholder': "Résumé affiché dans les listes (300 caractères max)",
            }),
            'content': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 14}),
            'category': forms.Select(attrs={'class': INPUT_CLASS}),
            'image': forms.ClearableFileInput(attrs={'class': 'text-sm text-gray-600'}),
            'status': forms.Select(attrs={'class': INPUT_CLASS}),
            'reading_time': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': '1'}),
        }
        labels = {
            'title': 'Titre',
            'excerpt': 'Résumé',
            'content': 'Contenu',
            'category': 'Catégorie',
            'image': 'Image de couverture',
            'status': 'Statut',
            'reading_time': 'Temps de lecture (min)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].required = False
        self.fields['excerpt'].required = False

    def save(self, commit=True):
        article = super().save(commit=False)
        if not article.slug:
            article.slug = self._unique_slug(article.title)
        if not article.excerpt:
            article.excerpt = article.content[:297] + '…' if len(article.content) > 297 else article.content
        # published_at pilote le tri des listes publiques : il doit exister dès la publication.
        if article.status == 'PUBLISHED' and not article.published_at:
            article.published_at = timezone.now()
        if commit:
            article.save()
        return article

    def _unique_slug(self, title):
        base = slugify(title) or 'article'
        slug, counter = base, 2
        while Article.objects.filter(slug=slug).exclude(pk=self.instance.pk).exists():
            slug = f'{base}-{counter}'
            counter += 1
        return slug
