from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from apps.core.permissions import can
from apps.core.models import AuditEvent
from .models import DuesRecord, DuesChange, DuesSchedule


def require(actor, capability, obj=None):
    if not can(actor, capability, obj):
        raise PermissionDenied


@transaction.atomic
def ensure_record(*, actor, profile, lions_year):
    require(actor, "dues.manage")
    record, _ = DuesRecord.objects.get_or_create(profile=profile, lions_year=lions_year)
    return record


@transaction.atomic
def set_dues_schedule(*, actor, lions_year, tranche1_amount, tranche2_amount):
    """Barème unique pour tous les membres d'une Année Lions — jamais de montant par
    membre. Protégé côté vue par une action explicite « Modifier les montants »."""
    require(actor, "dues.manage")
    for amount in (tranche1_amount, tranche2_amount):
        if amount is not None and amount < 0:
            raise ValidationError("Un montant ne peut pas être négatif.")
    schedule, _ = DuesSchedule.objects.select_for_update().get_or_create(lions_year=lions_year)
    schedule.tranche1_amount = tranche1_amount
    schedule.tranche2_amount = tranche2_amount
    schedule.updated_by = actor
    schedule.full_clean()
    schedule.save()
    AuditEvent.objects.create(actor=actor, action="dues.schedule_updated", object_type="DuesSchedule", object_id=str(schedule.pk))
    return schedule


@transaction.atomic
def set_tranche_paid(*, actor, record, tranche, paid, paid_on=None, motif=""):
    require(actor, "dues.manage")
    if tranche not in (1, 2):
        raise ValidationError("Tranche invalide.")
    record = DuesRecord.objects.select_for_update().get(pk=record.pk)
    field = f"tranche{tranche}_paid"
    date_field = f"tranche{tranche}_paid_on"
    old_paid = getattr(record, field)
    setattr(record, field, paid)
    setattr(record, date_field, paid_on if paid else None)
    if motif:
        record.note = motif[:300]
    record.full_clean()
    record.save()
    if old_paid != paid:
        DuesChange.objects.create(record=record, actor=actor, tranche=tranche, old_paid=old_paid, new_paid=paid, motif=motif[:300])
        AuditEvent.objects.create(actor=actor, action="dues.tranche_changed", object_type="DuesRecord", object_id=str(record.pk))
    return record
