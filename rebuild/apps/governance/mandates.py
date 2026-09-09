from django.db import transaction
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from apps.core.permissions import can
from apps.core.models import AuditEvent
from .models import Mandate, LionsYear

@transaction.atomic
def save_mandate(*, actor, data, mandate=None):
    get_user_model().objects.select_for_update().get(pk=actor.pk)
    if not can(actor, "mandate.manage"): raise PermissionDenied
    allowed = {"profile", "function", "lions_year", "starts_on", "ends_on"}
    if set(data) - allowed: raise ValidationError("Champs de mandat non autorisés.")
    if mandate: mandate = Mandate.objects.select_for_update().get(pk=mandate.pk)
    else: mandate = Mandate()
    for key, value in data.items(): setattr(mandate, key, value)
    LionsYear.objects.select_for_update().get(pk=mandate.lions_year_id)
    mandate.full_clean(); mandate.save()
    AuditEvent.objects.create(actor=actor, action="mandate.saved", object_type="Mandate", object_id=str(mandate.pk))
    return mandate
