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
from .models import ContactRequest, MemberEmailCampaign
from .forms import ApplicationForm,ContactForm, MemberBroadcastForm
from .services import submit,change_state, broadcast_recipients, queue_member_broadcast, resolve_broadcast_recipients
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
                return render(request,"espace/request_detail.html",{"item":obj,"kind":kind,"can_manage":can(request.user,kind+".manage",obj),"states":ContactRequest.STATES},status=400)
        return render(request,"espace/request_detail.html",{"item":obj,"kind":kind,"can_manage":can(request.user,kind+".manage",obj),"states":ContactRequest.STATES})
    if request.method=="POST":
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(["GET"])
    return render(request,"espace/requests.html",{"page_obj":Paginator(Model.objects.all(),20).get_page(request.GET.get("page")),"kind":kind})


@capability_required("communication.view_member_broadcast")
@require_http_methods(["GET", "POST"])
def member_broadcast(request):
    """Prévisualisation/test sans diffusion ; diffusion confirmée côté serveur.

    Le compteur affiché avant toute soumission (audience_options[*].count) n'est
    qu'indicatif : à chaque POST, le serveur reconstitue le véritable ensemble de
    destinataires depuis l'audience et les adresses supplémentaires validées — jamais
    depuis un total transmis par le navigateur."""
    initial = {"campaign_key": uuid4(), "audience": MemberEmailCampaign.Audience.ALL_ACTIVE}
    form = MemberBroadcastForm(request.POST or None, initial=initial)
    # Liste plutôt que dict : les templates Django n'indexent pas un dict par une clé
    # variable, et ce projet n'introduit pas de templatetag pour un simple lookup.
    audience_options = [{"value": value, "label": label, "count": len(broadcast_recipients(value))}
        for value, label in MemberEmailCampaign.Audience.choices]
    default_count = audience_options[0]["count"]
    counts = {"internal": default_count, "external": 0, "total": default_count}
    context = {"form": form, "counts": counts, "audience_options": audience_options}

    if request.method == "POST" and form.is_valid():
        action = request.POST.get("action")
        audience = form.cleaned_data["audience"]
        extra_emails = form.cleaned_data["extra_emails"]
        members, external = resolve_broadcast_recipients(audience, extra_emails)
        counts = {"internal": len(members), "external": len(external), "total": len(members) + len(external)}
        context["counts"] = counts
        draft = SimpleNamespace(subject=form.cleaned_data["subject"], body=form.cleaned_data["body"])

        if action == "preview":
            _, text_body, html_body = render_broadcast(draft, user=request.user)
            context.update(preview_html=html_body, preview_text=text_body)
            if external:
                # Aucune liste d'adresses affichée : uniquement le rendu générique
                # qu'un destinataire externe recevrait (« Bonjour, », sans prénom inventé).
                _, _, context["preview_external_html"] = render_broadcast(draft, user=None)
            return render(request, "espace/communication_broadcast.html", context)

        if action == "test":
            subject, text_body, html_body = render_broadcast(draft, user=request.user)
            message = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [request.user.email])
            message.attach_alternative(html_body, "text/html")
            message.send(fail_silently=True)
            messages.success(request, "E-mail test envoyé uniquement à votre adresse.")
            return redirect("communications:broadcast")

        if action == "confirm":
            # Liste des adresses supplémentaires visible ici uniquement : l'auteur relit
            # sa propre saisie avant un envoi irréversible (utile pour repérer une faute
            # de frappe) — jamais affichée aux destinataires ni dans l'historique général.
            context["audience_label"] = dict(MemberEmailCampaign.Audience.choices)[audience]
            context["external_emails"] = external
            return render(request, "espace/communication_confirm.html", context)

        if action == "send" and request.POST.get("confirmed") == "yes":
            campaign, created = queue_member_broadcast(
                actor=request.user, subject=form.cleaned_data["subject"], body=form.cleaned_data["body"],
                idempotency_key=form.cleaned_data["campaign_key"], audience=audience, extra_emails=external,
            )
            if created:
                messages.success(request, f"Votre e-mail a été placé dans la file pour {campaign.recipient_count} destinataire(s).")
            else:
                messages.info(request, "Cet envoi avait déjà été confirmé ; aucune campagne supplémentaire n’a été créée.")
            return redirect("communications:broadcast_history")

        # action == "back" (retour depuis l'écran de confirmation) ou valeur inconnue :
        # on revient au formulaire de composition, rien n'est perdu.
    return render(request, "espace/communication_broadcast.html", context)


@capability_required("communication.view_member_broadcast")
@require_safe
def member_broadcast_history(request):
    return render(request, "espace/communication_history.html", {
        "page_obj": Paginator(MemberEmailCampaign.objects.select_related("created_by"), 20).get_page(request.GET.get("page")),
    })
