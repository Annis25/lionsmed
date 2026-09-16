"""Filtres de présentation pour les cartes documents — aucune donnée inventée,
uniquement des libellés courts dérivés de champs déjà stockés (content_type)."""
from django import template
from ..views import PREVIEWABLE_CONTENT_TYPES

register = template.Library()

_KIND_LABELS = {
    "application/pdf": "PDF",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "Excel",
    "image/png": "PNG",
    "image/jpeg": "JPEG",
}


@register.filter
def file_kind(content_type):
    return _KIND_LABELS.get(content_type, "Fichier")


@register.filter
def is_previewable(document):
    return document.content_type in PREVIEWABLE_CONTENT_TYPES
