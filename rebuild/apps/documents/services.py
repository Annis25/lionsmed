import uuid
from pathlib import Path
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from apps.core.permissions import can
from apps.core.models import AuditEvent
from .models import Document, DocumentGrant
from .storage import document_storage

MAX_BYTES = 15 * 1024 * 1024
# Extension et MIME annoncé doivent concorder ; contrôle basique, aucun antivirus externe branché.
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


@transaction.atomic
def upload_document(*, actor, upload, title, description, category, visibility, lions_year=None):
    require(actor, "document.manage")
    if category not in Document.Category.values or visibility not in Document.Visibility.values:
        raise ValidationError("Catégorie ou visibilité invalide.")
    suffix = Path(upload.name).suffix.lower()
    expected = ALLOWED.get(suffix)
    if not expected or upload.content_type != expected:
        raise ValidationError("Format de document non autorisé (PDF, DOCX, XLSX, PNG ou JPEG attendu).")
    if upload.size > MAX_BYTES:
        raise ValidationError("Le document doit peser au maximum 15 Mo.")
    raw = upload.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValidationError("Le document doit peser au maximum 15 Mo.")
    key = f"{uuid.uuid4()}{suffix}"
    document_storage().save(key, ContentFile(raw))
    document = Document(title=title[:180], description=description[:2000], category=category, visibility=visibility,
        status=Document.Status.AVAILABLE, storage_key=key, original_filename=Path(upload.name).name[:255],
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
