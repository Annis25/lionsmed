from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404
from django.utils import timezone
from apps.core.permissions import can, effective_role, MEMBERS, MANAGERS, BUREAU_LEVEL
from .models import Document, DocumentGrant


def require(actor, capability, obj=None):
    if not can(actor, capability, obj):
        raise PermissionDenied


def scope_documents(actor):
    """ACL identique pour liste, détail, HEAD et téléchargement : toujours ce selector."""
    require(actor, "document.view")
    role = effective_role(actor)
    tiers = []
    if role in MEMBERS:
        tiers.append(Document.Visibility.MEMBERS)
    if role in BUREAU_LEVEL:
        tiers.append(Document.Visibility.BUREAU)
    if role in MANAGERS:
        tiers.append(Document.Visibility.RESPONSABLES)
    now = timezone.now()
    granted = DocumentGrant.objects.filter(user_id=actor.pk).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now)).values("document_id")
    return Document.objects.filter(status=Document.Status.AVAILABLE).filter(Q(visibility__in=tiers) | Q(pk__in=granted)).select_related("lions_year")


def document_for_actor(actor, document_id):
    try:
        return scope_documents(actor).get(pk=document_id)
    except Document.DoesNotExist:
        raise Http404
