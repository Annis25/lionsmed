import base64
import hashlib
import re
from functools import wraps
from uuid import uuid4
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_http_methods, require_safe
from apps.communications.selectors import delivery_enabled
from apps.core.permissions import capability_required
from . import catalog
from .access import holders, mailboxes_for
from .forms import ComposeForm
from .models import InboundEmail, OutgoingEmail
from .selectors import inbox_rows, mailbox_tabs, outgoing_recipients, readers, sent_rows, sync_status
from .services import mark_unread, open_message, retry_failed, send_message

PER_PAGE = 25
QUOTE_LIMIT = 4000


def mailbox_view(view):
    """Résout la boîte de l'URL et revérifie l'accès à chaque requête, quelle que soit la page :
    une adresse fabriquée à la main aboutit à 404 (boîte inconnue) ou 403 (boîte d'une autre fonction)."""
    @capability_required("account.access_private_area")
    @wraps(view)
    def wrapped(request, slug, *args, **kwargs):
        mailbox = catalog.get(slug)
        if mailbox is None:
            raise Http404
        allowed = mailboxes_for(request.user)
        if mailbox not in allowed:
            raise PermissionDenied
        request.mailboxes = allowed
        return view(request, mailbox, *args, **kwargs)
    return wrapped


def _context(request, mailbox, folder, **extra):
    return {"mailbox": mailbox, "tabs": mailbox_tabs(request.mailboxes, mailbox), "folder": folder,
            "unread_count": InboundEmail.objects.filter(mailbox=mailbox.key, read_at__isnull=True).count(), **extra}


@capability_required("account.access_private_area")
@require_safe
def home(request):
    allowed = mailboxes_for(request.user)
    if not allowed:
        raise PermissionDenied
    return redirect("mailboxes:inbox", slug=allowed[0].key)


@mailbox_view
@require_safe
def inbox(request, mailbox):
    page = Paginator(InboundEmail.objects.filter(mailbox=mailbox.key).defer("body_text", "body_html", "references"),
                     PER_PAGE).get_page(request.GET.get("page"))
    return render(request, "espace/mailbox_inbox.html", _context(
        request, mailbox, "inbox", page_obj=page, rows=inbox_rows(page.object_list), sync=sync_status(mailbox),
        shared=len(holders(mailbox)) > 1))


def _theme_script_hash():
    """Empreinte du seul script en ligne du site (choix du thème), pour l'autoriser nommément."""
    try:
        source = (settings.BASE_DIR / "templates" / "base" / "site.html").read_text(encoding="utf-8")
    except OSError:
        return ""
    match = re.search(r"<script data-theme-init>(.*?)</script>", source, re.S)
    return "'sha256-" + base64.b64encode(hashlib.sha256(match.group(1).encode()).digest()).decode() + "'" if match else ""


# Seconde barrière derrière le nettoyeur : sur la page qui affiche un e-mail reçu, le navigateur
# ne charge aucune ressource extérieure (pas de pixel de suivi) et n'exécute aucun script étranger.
MESSAGE_CSP = ("default-src 'none'; script-src 'self' " + _theme_script_hash() + "; style-src 'self' https://fonts.googleapis.com; "
               "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
               "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")


@mailbox_view
@require_safe
def message(request, mailbox, email_id):
    # Le filtre sur la boîte fait qu'un identifiant de message d'une autre boîte n'existe pas ici.
    email = get_object_or_404(InboundEmail, pk=email_id, mailbox=mailbox.key)
    email = open_message(actor=request.user, mailbox=mailbox, email=email)
    response = render(request, "espace/mailbox_message.html", _context(
        request, mailbox, "inbox", email=email,
        # body_html n'est écrit que par sanitizer.clean_html (liste blanche de balises, sans attribut d'origine).
        body_html=mark_safe(email.body_html) if email.body_html else "",
        # Qui a ouvert le message : utile dès que la boîte a plusieurs titulaires.
        readers=readers(email) if len(holders(mailbox)) > 1 else [],
        reply_all=len(email.recipients) + len(email.copies) > 1))
    response["Content-Security-Policy"] = MESSAGE_CSP
    return response


@mailbox_view
@require_http_methods(["POST"])
def unread(request, mailbox, email_id):
    email = get_object_or_404(InboundEmail, pk=email_id, mailbox=mailbox.key)
    mark_unread(actor=request.user, mailbox=mailbox, email=email)
    messages.info(request, "Message marqué comme non lu.")
    return redirect("mailboxes:inbox", slug=mailbox.key)


def _reply_initial(mailbox, email, everyone):
    """Réponse préremplie : destinataire, objet et citation du message d'origine."""
    subject = email.subject if email.subject.lower().startswith("re:") else "Re: " + email.subject
    sender = email.reply_to or email.sender_address
    copies = []
    if everyone:
        skipped = {mailbox.address.lower(), sender.lower()}
        copies = [row["address"] for row in email.recipients + email.copies if row["address"].lower() not in skipped]
    quoted = "\n".join("> " + line for line in email.body_text[:QUOTE_LIMIT].splitlines())
    author = email.sender_name or email.sender_address
    intro = f"Le {timezone.localtime(email.received_at):%d/%m/%Y à %H:%M}, {author} a écrit :"
    return {"to": sender, "cc": ", ".join(copies), "subject": subject[:180], "body": f"\n\n\n{intro}\n{quoted}"}


@mailbox_view
@require_http_methods(["GET", "POST"])
def compose(request, mailbox):
    original = None
    if request.GET.get("reponse"):
        try:
            original = InboundEmail.objects.filter(pk=request.GET["reponse"], mailbox=mailbox.key).first()
        except (ValidationError, ValueError):
            original = None
        if original is None:
            raise Http404
    initial = {"message_key": uuid4()}
    if original is not None:
        initial.update(_reply_initial(mailbox, original, request.GET.get("tous") == "1"))
    form = ComposeForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            outgoing, created = send_message(actor=request.user, mailbox=mailbox, to=form.cleaned_data["to"],
                cc=form.cleaned_data["cc"], subject=form.cleaned_data["subject"], body=form.cleaned_data["body"],
                idempotency_key=form.cleaned_data["message_key"], in_reply_to=original)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            if created:
                messages.success(request, "Votre message est dans la file d’envoi. Il part de " + mailbox.address + ".")
            else:
                messages.info(request, "Ce message avait déjà été envoyé ; aucun second envoi n’a été créé.")
            return redirect("mailboxes:sent_detail", slug=mailbox.key, outgoing_id=outgoing.pk)
    return render(request, "espace/mailbox_compose.html", _context(
        request, mailbox, "compose", form=form, original=original, delivery_enabled=delivery_enabled()))


@mailbox_view
@require_safe
def sent(request, mailbox):
    page = Paginator(OutgoingEmail.objects.filter(mailbox=mailbox.key).select_related("author"),
                     PER_PAGE).get_page(request.GET.get("page"))
    return render(request, "espace/mailbox_sent.html", _context(
        request, mailbox, "sent", page_obj=page, rows=sent_rows(page.object_list)))


@mailbox_view
@require_http_methods(["GET", "POST"])
def sent_detail(request, mailbox, outgoing_id):
    outgoing = get_object_or_404(OutgoingEmail.objects.select_related("author", "in_reply_to"), pk=outgoing_id, mailbox=mailbox.key)
    if request.method == "POST":
        retried = retry_failed(actor=request.user, mailbox=mailbox, outgoing=outgoing)
        if retried:
            messages.success(request, f"{retried} envoi{'s' if retried > 1 else ''} remis en file.")
        else:
            messages.info(request, "Aucun échec à relancer pour ce message.")
        return redirect("mailboxes:sent_detail", slug=mailbox.key, outgoing_id=outgoing.pk)
    recipients = outgoing_recipients(outgoing)
    return render(request, "espace/mailbox_sent_detail.html", _context(
        request, mailbox, "sent", outgoing=outgoing, recipients=recipients, row=sent_rows([outgoing])[0],
        retryable_count=sum(1 for row in recipients if row["retryable"]), delivery_enabled=delivery_enabled()))
