"""Rendu centralisé des e-mails Lionsmed.

Les modèles HTML et texte reçoivent toujours les mêmes données sûres. Les URL sont
construites depuis SITE_ORIGIN : aucune valeur HTTP contrôlée par un visiteur n'est
utilisée.
"""
from urllib.parse import urljoin

from django.conf import settings
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.utils.html import strip_tags


SUBJECTS = {
    "APPLICATION": "Candidature reçue — Lions Club Sfax-Méditerranée",
    "CONTACT": "Nouveau message de contact — Lions Club Sfax-Méditerranée",
    "EVENT_REMINDER": "Rappel de rendez-vous — Lions Club Sfax-Méditerranée",
    "IMPORTANT": "Notification importante — Lions Club Sfax-Méditerranée",
    "DOCUMENT": "Nouveau document disponible — Lions Club Sfax-Méditerranée",
    "VOTE_OPENED": "Ouverture d’un vote — Lions Club Sfax-Méditerranée",
    "VOTE_RESULTS": "Résultats du vote — Lions Club Sfax-Méditerranée",
    "SATISFACTION_OPENED": "Satisfaction du mois — Lions Club Sfax-Méditerranée",
    "ACTIVATION": "Bienvenue au Lions Club Sfax-Méditerranée",
}

STEMS = {
    "APPLICATION": "application_receipt", "CONTACT": "contact_notice",
    "EVENT_REMINDER": "event_reminder", "IMPORTANT": "notification_important",
    "DOCUMENT": "notification_document", "VOTE_OPENED": "ouverture_vote",
    "VOTE_RESULTS": "resultats_vote", "SATISFACTION_OPENED": "satisfaction",
    "ACTIVATION": "member_activation",
}


def absolute(path):
    return urljoin(settings.SITE_ORIGIN.rstrip("/") + "/", path.lstrip("/"))


def first_name(user):
    value = (getattr(user, "first_name", "") or "").strip()
    return value[:80]


def recipient_for_email(address):
    return get_user_model().objects.filter(email__iexact=address, is_active=True).first()


def base_context(user=None, **extra):
    return {
        "origin": settings.SITE_ORIGIN,
        "logo_url": absolute("/static/images/emblem-256.png"),
        "first_name": first_name(user) if user else "",
        **extra,
    }


def render_transactional(kind, *, user=None, **extra):
    """Retourne subject, text/plain et HTML, avec contenu minimal et fiable."""
    stem = STEMS[kind]
    context = base_context(user, **extra)
    return (
        SUBJECTS[kind],
        render_to_string(f"emails/{stem}.txt", context),
        render_to_string(f"emails/{stem}.html", context),
    )


def render_broadcast(campaign, *, user):
    context = base_context(user, campaign=campaign, message_html=campaign.body)
    return (
        campaign.subject,
        render_to_string("emails/member_broadcast.txt", context),
        render_to_string("emails/member_broadcast.html", context),
    )


def safe_subject(value):
    value = strip_tags(value or "").replace("\r", "").replace("\n", " ").strip()
    return " ".join(value.split())[:180]
