from django.utils import timezone
from apps.core.models import PublicImage
from apps.service_actions.models import Action
from apps.agenda.models import Event
from .models import NewsArticle,EditorialSection,ClubIdentity
from . import identity

def public_qs(model):return model.objects.public().select_related("cover","social_image")

def institution():
    item=ClubIdentity.objects.filter(validated_at__isnull=False).first()
    return {"name":identity.NAME,"city":identity.CITY,"country":identity.COUNTRY,"district":identity.DISTRICT,"affiliation":identity.AFFILIATION,"motto":identity.MOTTO,
        "email":item.contact_email if item else "","phone":item.phone if item else "","address":item.postal_address if item else ""}

def sections():return {s.key:s for s in EditorialSection.objects.filter(validated_at__isnull=False)}

def image_is_public(image):
    if not image.approved_at:return False
    from django.db.models import Q
    for model in [Action,NewsArticle,Event]:
        if model.objects.public().filter(Q(cover=image)|Q(social_image=image)).exists():return True
    return Action.objects.public().filter(photos__image=image).exists()
