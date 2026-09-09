from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods, require_safe
from apps.core.permissions import capability_required
from .selectors import scope_documents, document_for_actor, require
from .services import upload_document, grant_access, revoke_access
from .forms import DocumentForm, DocumentGrantForm
from .storage import document_storage
from .models import Document, DocumentGrant


@capability_required("document.view")
@require_safe
def document_list(request):
    qs = scope_documents(request.user)
    category = request.GET.get("category", "")
    if category in Document.Category.values:
        qs = qs.filter(category=category)
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(request, "espace/documents.html", {"page_obj": page, "categories": Document.Category.choices})


@capability_required("document.view")
@require_safe
def document_detail(request, document_id):
    return render(request, "espace/document_detail.html", {"document": document_for_actor(request.user, document_id)})


def _download_response(request, document):
    if request.method == "HEAD":
        response = HttpResponse(content_type=document.content_type)
        response["Content-Length"] = str(document.size)
    else:
        try:
            handle = document_storage().open(document.storage_key, "rb")
        except FileNotFoundError:
            raise Http404
        response = FileResponse(handle, content_type=document.content_type, filename=document.original_filename, as_attachment=True)
    response["Cache-Control"] = "private, no-store"
    response["X-Robots-Tag"] = "noindex"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@capability_required("document.view")
@require_http_methods(["GET", "HEAD"])
def document_download(request, document_id):
    # Même selector qu'en liste/détail : l'ACL de téléchargement ne diverge jamais.
    document = document_for_actor(request.user, document_id)
    return _download_response(request, document)


@capability_required("document.manage")
@require_http_methods(["GET", "POST"])
def document_upload(request):
    form = DocumentForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            document = upload_document(actor=request.user, upload=form.cleaned_data["file"], title=form.cleaned_data["title"],
                description=form.cleaned_data["description"], category=form.cleaned_data["category"], visibility=form.cleaned_data["visibility"])
            messages.success(request, "Document déposé et disponible.")
            return redirect("documents:manage_detail", document_id=document.pk)
        except ValidationError as error:
            form.add_error("file", error)
    return render(request, "espace/document_upload.html", {"form": form})


@capability_required("document.manage")
@require_safe
def manage_list(request):
    page = Paginator(Document.objects.all().order_by("-created_at"), 20).get_page(request.GET.get("page"))
    return render(request, "espace/document_manage_list.html", {"page_obj": page})


@capability_required("document.manage")
@require_http_methods(["GET", "POST"])
def manage_detail(request, document_id):
    document = get_object_or_404(Document, pk=document_id)
    require(request.user, "document.manage")
    form = DocumentGrantForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            user = get_user_model().objects.get(email=form.cleaned_data["email"].strip().lower())
            grant_access(actor=request.user, document=document, user=user, expires_at=form.cleaned_data["expires_at"])
            messages.success(request, "Accès accordé.")
            return redirect("documents:manage_detail", document_id=document.pk)
        except get_user_model().DoesNotExist:
            form.add_error("email", "Aucun compte avec cette adresse.")
    return render(request, "espace/document_manage_detail.html", {"document": document, "form": form, "grants": document.grants.select_related("user")})


@capability_required("document.manage")
@require_http_methods(["POST"])
def manage_revoke(request, document_id, grant_id):
    document = get_object_or_404(Document, pk=document_id)
    grant = get_object_or_404(DocumentGrant, pk=grant_id, document=document)
    revoke_access(actor=request.user, grant=grant)
    messages.success(request, "Accès révoqué.")
    return redirect("documents:manage_detail", document_id=document.pk)
