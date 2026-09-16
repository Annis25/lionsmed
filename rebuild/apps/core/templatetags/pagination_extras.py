"""Filtre unique : le template ne peut pas appeler Paginator.get_elided_page_range()
avec son argument via la simple notation par points (`{% querystring %}`, lui, est un
tag Django natif — pas besoin de filtre pour ça). Utilisé uniquement par
components/private/pagination.html.
"""
from django import template

register = template.Library()


@register.filter
def elided_page_range(paginator, number):
    return paginator.get_elided_page_range(number)
