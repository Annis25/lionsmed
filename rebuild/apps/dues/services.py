from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from apps.core.permissions import can
from apps.core.models import AuditEvent
from .models import DuesRecord, DuesChange


def require(actor, capability, obj=None):
    if not can(actor, capability, obj):
        raise PermissionDenied


@transaction.atomic
def ensure_record(*, actor, profile, lions_year):
    require(actor, "dues.manage")
    record, _ = DuesRecord.objects.get_or_create(profile=profile, lions_year=lions_year)
    return record


@transaction.atomic
def record_dues_status(*, actor, record, status, amount, paid_on, motif):
    require(actor, "dues.manage")
    if status not in DuesRecord.Status.values:
        raise ValidationError("Statut invalide.")
    if not motif or not motif.strip():
        raise ValidationError("Un motif est requis pour toute correction.")
    record = DuesRecord.objects.select_for_update().get(pk=record.pk)
    old_status, old_amount = record.status, record.amount
    record.status = status
    record.amount = amount
    record.paid_on = paid_on
    record.note = motif[:300]
    record.full_clean()
    record.save()
    DuesChange.objects.create(record=record, actor=actor, old_status=old_status, new_status=status,
        old_amount=old_amount, new_amount=amount, motif=motif[:300])
    AuditEvent.objects.create(actor=actor, action="dues.status_changed", object_type="DuesRecord", object_id=str(record.pk))
    return record
