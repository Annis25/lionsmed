import uuid
from pathlib import Path
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from apps.core.permissions import can
from apps.core.models import AuditEvent
from .models import Document, DocumentGrant
from .storage import document_storage
from .office_validation import validate_structure
from .scanning import scan_bytes, ScannerUnavailable

MAX_BYTES = 50 * 1024 * 1024
# Extension et MIME annoncé doivent concorder ; complété par la signature/structure (office_validation)
# puis par l'analyse antivirus (scanning) avant toute disponibilité — échec fermé sur chaque étage.
ALLOWED = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def require(actor, capability, obj=None):
    if not can(actor, capability, obj):
        raise PermissionDenied


def audit(actor, action, obj):
    AuditEvent.objects.create(actor=actor, action=action, object_type=obj._meta.object_name, object_id=str(obj.pk))


def upload_document(*, actor, upload, title, description, category, visibility, lions_year=None):
    # Validation, structure et antivirus se font hors transaction : un rejet (y compris
    # infecté) doit laisser une trace auditée durable, jamais annulée par un rollback.
    require(actor, "document.manage")
    if category not in Document.Category.values or visibility not in Document.Visibility.values:
        raise ValidationError("Catégorie ou visibilité invalide.")
    suffix = Path(upload.name).suffix.lower()
    expected = ALLOWED.get(suffix)
    if not expected or upload.content_type != expected:
        raise ValidationError("Format de document non autorisé (PDF, DOCX, XLSX, PNG ou JPEG attendu).")
    if upload.size > MAX_BYTES:
        raise ValidationError("Le document doit peser au maximum 50 Mo.")
    raw = upload.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValidationError("Le document doit peser au maximum 50 Mo.")
    validate_structure(raw, suffix)
    try:
        result = scan_bytes(raw)
    except ScannerUnavailable as error:
        # Échec fermé : sans scanner joignable, aucun document ne devient disponible.
        raise ValidationError("Analyse antivirus indisponible : dépôt refusé, réessayez plus tard.") from error
    if not result.clean:
        AuditEvent.objects.create(actor=actor, action="document.upload_rejected_infected", object_type="Document", object_id="")
        raise ValidationError("Document rejeté par l'analyse antivirus.")
    return _store_document(actor=actor, raw=raw, suffix=suffix, expected=expected, upload_name=upload.name,
        title=title, description=description, category=category, visibility=visibility, lions_year=lions_year)


@transaction.atomic
def _store_document(*, actor, raw, suffix, expected, upload_name, title, description, category, visibility, lions_year):
    key = f"{uuid.uuid4()}{suffix}"
    document_storage().save(key, ContentFile(raw))
    document = Document(title=title[:180], description=description[:2000], category=category, visibility=visibility,
        status=Document.Status.AVAILABLE, storage_key=key, original_filename=Path(upload_name).name[:255],
        content_type=expected, size=len(raw), author=actor, lions_year=lions_year)
    document.full_clean()
    document.save()
    audit(actor, "document.uploaded", document)
    return document


@transaction.atomic
def grant_access(*, actor, document, user, expires_at=None):
    require(actor, "document.manage")
    grant, _ = DocumentGrant.objects.update_or_create(document=document, user=user, defaults={"expires_at": expires_at, "granted_by": actor})
    audit(actor, "document.grant_set", grant)
    return grant


@transaction.atomic
def revoke_access(*, actor, grant):
    require(actor, "document.manage")
    document = grant.document
    grant.delete()
    audit(actor, "document.grant_revoked", document)
