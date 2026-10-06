from uuid import uuid4
from types import SimpleNamespace
from django.conf import settings
from django.contrib import messages
from django.core.mail import EmailMultiAlternatives
from django.core import signing
from django.shortcuts import render,redirect,get_object_or_404
from django.views.decorators.http import require_http_methods,require_safe
from django.views.decorators.debug import sensitive_post_parameters
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from apps.core.permissions import capability_required,can
from apps.core.throttling import consume
from apps.editorial.views import public_context
from apps.editorial.publication import require
from apps.members.models import MembershipApplication
from .models import ContactRequest
from .forms import ApplicationForm,ContactForm, MemberBroadcastForm
from .services import (submit, change_state, eligible_broadcast_members, queue_member_broadcast,
    resolve_broadcast_selection, retry_failed_broadcast)
from .selectors import campaign_recipients, delivery_enabled, selectable_members, visible_campaigns, with_tracking
from .emailing import render_broadcast

@sensitive_post_parameters()
@require_http_methods(["GET","POST"])
def public_form(request,kind):
    Form=ApplicationForm if kind=="application" else ContactForm
    title,description=("Déposer une candidature","Quelques informations suffisent pour faire connaissance et commencer l’échange.") if kind=="application" else ("Contact","Une question, un projet ou une proposition ? Écrivez-nous.")
    initial={"submission_token":signing.dumps({"id":str(uuid4()),"kind":kind},salt="public-submission")}
    form=Form(request.POST if request.method=="POST" else None,initial=initial)
    context=public_context(request,title,description,indexable=kind!="application")
    if request.method=="POST":
        if not consume(kind+"-ip",request.META.get("REMOTE_ADDR","unknown"),limit=5,seconds=900):
            context.update(form=form,kind=kind,limited=True);request.public_indexable=False
            return render(request,"public/submission.html",context,status=429)
        if form.is_valid():
            if consume(kind+"-email",form.cleaned_data["email"],limit=3,seconds=3600):
                submit(form)
                return redirect("communications:"+kind+"_done")
            form.add_error(None,"Veuillez attendre avant de déposer une nouvelle demande.")
    context.update(form=form,kind=kind)
    return render(request,"public/submission.html",context)

@require_safe
def done(request,kind):
    context=public_context(request,"Demande reçue","Votre demande a été enregistrée. Merci pour votre message.",indexable=False)
    context["kind"]=kind
    return render(request,"public/submission_done.html",context)

def _request_context(request,obj,kind):
    # « Origine » est stockée sous forme de code : on affiche le libellé du formulaire public.
    origins=dict(ApplicationForm.base_fields["origin"].choices)
    return {"item":obj,"kind":kind,"can_manage":can(request.user,kind+".manage",obj),"states":ContactRequest.STATES,
        "origin_label":origins.get(getattr(obj,"origin",""),getattr(obj,"origin",""))}

@capability_required("account.access_private_area")
@require_http_methods(["GET","POST"])
def inbox(request,kind,object_id=None):
    require(request.user,kind+".view")
    Model=MembershipApplication if kind=="application" else ContactRequest
    if object_id:
        obj=get_object_or_404(Model,pk=object_id)
        if request.method=="POST":
            try:
                change_state(actor=request.user,obj=obj,state=request.POST.get("state"))
                return redirect("communications:inbox",kind=kind)
            except ValidationError as error:
                from django.contrib import messages
                messages.error(request," ".join(error.messages))
                return render(request,"espace/request_detail.html",_request_context(request,obj,kind),status=400)
        return render(request,"espace/request_detail.html",_request_context(request,obj,kind))
    if request.method=="POST":
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(["GET"])
    return render(request,"espace/requests.html",{"page_obj":Paginator(Model.objects.all(),20).get_page(request.GET.get("page")),"kind":kind})


def _draft_counts(form, eligible):
    """Valeurs initiales du résumé pour un brouillon pas encore validé, avant que
    communication.js ne prenne le relais : jamais utilisées pour envoyer, l'envoi
    recalcule toujours ses destinataires depuis une saisie valide."""
    posted = set(form["members"].value() or [])
    members = [user for user, _ in eligible if str(user.pk) in posted]
    seen = {user.email.lower() for user in members}
    external = 0
    for token in (form["extra_emails"].value() or "").replace(",", " ").replace(";", " ").split():
        if token.lower() not in seen:
            seen.add(token.lower())
            external += 1
    return {"internal": len(members), "external": external, "duplicates": 0, "total": len(members) + external}


def _broadcast_action(request, form, action, members, external, context):
    """Exécute l'action demandée sur un brouillon valide ; renvoie une réponse HTTP, ou
    None pour réafficher la rédaction (aperçu, test, « Modifier », action inconnue)."""
    draft = SimpleNamespace(subject=form.cleaned_data["subject"], body=form.cleaned_data["body"])

    if action == "preview":
        _, text_body, html_body = render_broadcast(draft, user=request.user)
        context.update(preview_html=html_body, preview_text=text_body)
        if external:
            # Aucune liste d'adresses affichée : uniquement le rendu générique
            # qu'un destinataire externe recevrait (« Bonjour, », sans prénom inventé).
            _, _, context["preview_external_html"] = render_broadcast(draft, user=None)

    elif action == "test":
        subject, text_body, html_body = render_broadcast(draft, user=request.user)
        message = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [request.user.email])
        message.attach_alternative(html_body, "text/html")
        # Réaffichage sur place, sans redirection : le brouillon et la sélection sont
        # conservés. Le résultat annoncé est le résultat réel, jamais un succès supposé.
        if not delivery_enabled():
            messages.warning(request, "L’envoi d’e-mails est désactivé sur cet environnement : aucun test n’a été envoyé.")
        elif message.send(fail_silently=True):
            messages.success(request, "E-mail test envoyé uniquement à votre adresse.")
        else:
            messages.error(request, "Le test n’a pas pu être envoyé. Réessayez dans quelques minutes.")

    elif action == "confirm":
        # Noms et adresses visibles ici : l'auteur relit sa propre sélection avant un
        # envoi irréversible (utile pour repérer une erreur de destinataire ou une
        # faute de frappe) — jamais repris dans la liste générale de l'historique.
        _, _, preview_html = render_broadcast(draft, user=request.user if members else None)
        context.update(members=members, external_emails=external, preview_html=preview_html,
                       delivery_enabled=delivery_enabled())
        return render(request, "espace/communication_confirm.html", context)

    elif action == "send" and request.POST.get("confirmed") == "yes":
        try:
            campaign, created = queue_member_broadcast(
                actor=request.user, subject=draft.subject, body=draft.body,
                idempotency_key=form.cleaned_data["campaign_key"],
                member_ids=[member.pk for member in members], extra_emails=external,
            )
        except ValidationError as error:
            form.add_error(None, error)
            return None
        if created:
            messages.success(request, f"Votre message est dans la file d’envoi pour {campaign.recipient_count} destinataire{'s' if campaign.recipient_count > 1 else ''}.")
        else:
            messages.info(request, "Cet envoi avait déjà été confirmé ; aucun second envoi n’a été créé.")
        return redirect("communications:broadcast_detail", campaign_id=campaign.pk)
    return None


@capability_required("communication.view_member_broadcast")
@require_http_methods(["GET", "POST"])
def member_broadcast(request):
    """Rédaction → vérification → envoi, sur une seule route et sans brouillon stocké.

    Aperçu et test ne diffusent rien. À chaque POST, le serveur reconstitue le véritable
    ensemble de destinataires depuis les membres cochés et les adresses externes validées
    — jamais depuis un total ou une liste calculés par le navigateur."""
    from apps.mailboxes.access import sender_for
    eligible = eligible_broadcast_members()
    action = request.POST.get("action", "")
    form = MemberBroadcastForm(request.POST or None, initial={"campaign_key": uuid4()},
        eligible=eligible, require_recipients=action in {"confirm", "send"})
    # Adresse d'envoi annoncée à l'auteur : la boîte de sa fonction, sinon l'adresse générale.
    context = {"form": form, "counts": _draft_counts(form, eligible), "sender_mailbox": sender_for(request.user)}

    if request.method == "POST" and form.is_valid():
        try:
            members, external = resolve_broadcast_selection(form.cleaned_data["members"], form.cleaned_data["extra_emails"])
        except ValidationError as error:
            # Éligibilité modifiée entre la validation du formulaire et ce recalcul.
            form.add_error(None, error)
        else:
            # « Doublons ignorés » : adresses saisies deux fois, ou identiques à celle d'un
            # membre sélectionné — jamais un second message pour la même adresse.
            context["counts"] = {"internal": len(members), "external": len(external),
                "duplicates": form.extra_emails_submitted - len(external), "total": len(members) + len(external)}
            response = _broadcast_action(request, form, action, members, external, context)
            if response is not None:
                return response

    context["member_rows"] = selectable_members(eligible, form["members"].value() or [])
    context["responsible_count"] = sum(1 for row in context["member_rows"] if row["responsible"])
    return render(request, "espace/communication_broadcast.html", context)


@capability_required("communication.view_member_broadcast")
@require_safe
def member_broadcast_history(request):
    from apps.mailboxes.access import sender_for
    page = Paginator(visible_campaigns(request.user).select_related("created_by"), 20).get_page(request.GET.get("page"))
    return render(request, "espace/communication_history.html", {
        "page_obj": page, "campaigns": with_tracking(page.object_list), "sender_mailbox": sender_for(request.user),
        "sees_all": can(request.user, "communication.view_all_member_broadcasts")})


@capability_required("communication.view_member_broadcast")
@require_http_methods(["GET", "POST"])
def member_broadcast_detail(request, campaign_id):
    """Suivi par destinataire d'une campagne ; POST = relance de ses échecs de livraison."""
    # Une communication d'une autre fonction n'existe pas pour ce compte, même avec son adresse exacte.
    campaign = get_object_or_404(visible_campaigns(request.user).select_related("created_by"), pk=campaign_id)
    if request.method == "POST":
        retried = retry_failed_broadcast(actor=request.user, campaign=campaign)
        if retried:
            messages.success(request, f"{retried} message{'s' if retried > 1 else ''} remis en file d’envoi.")
        else:
            messages.info(request, "Aucun échec à relancer pour cette communication.")
        return redirect("communications:broadcast_detail", campaign_id=campaign.pk)
    recipients = campaign_recipients(campaign)
    with_tracking([campaign])
    from apps.mailboxes import catalog
    return render(request, "espace/communication_detail.html", {
        "campaign": campaign, "recipients": recipients, "sender_mailbox": catalog.get(campaign.sender_mailbox),
        "retryable_count": sum(1 for row in recipients if row["retryable"]),
        "can_send": can(request.user, "communication.send_member_broadcast"),
        "delivery_enabled": delivery_enabled(),
    })
