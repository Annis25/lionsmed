from uuid import uuid4
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
from .forms import ApplicationForm,ContactForm
from .services import submit,change_state

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
