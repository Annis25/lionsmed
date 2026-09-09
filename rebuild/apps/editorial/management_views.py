from django.shortcuts import render,redirect,get_object_or_404
from django.views.decorators.http import require_http_methods,require_safe
from django.core.exceptions import ValidationError
from django.db import transaction,IntegrityError
from django.contrib import messages
from django.utils import timezone
from django.core.paginator import Paginator
from apps.core.permissions import capability_required,can
from apps.core.models import PublicImage
from apps.service_actions.models import Action,ActionPhoto
from apps.service_actions.forms import ActionForm
from apps.agenda.models import Event
from apps.agenda.forms import EventForm
from .models import EditorialSection,ClubIdentity,ImpactMetric
from .management_forms import ImageForm,SectionForm,IdentityForm,MetricForm
from .publication import require,save_content,publish_content,withdraw_content,audit
from .images import upload_image

TYPES={"action":(Action,ActionForm,"Actions"),"event":(Event,EventForm,"Événements")}

@capability_required("public_content.access_management")
@require_safe
def dashboard(request):
    return render(request,"espace/public_content.html",{"sections":EditorialSection.objects.all(),"metrics":ImpactMetric.objects.all(),"can_requests":can(request.user,"application.view") or can(request.user,"contact.view")})

@capability_required("public_content.access_management")
@require_safe
def content_list(request,kind):
    from django.http import Http404
    if kind not in TYPES:raise Http404
    Model,Form,title=TYPES[kind];require(request.user,kind+".edit")
    return render(request,"espace/content_list.html",{"page_obj":Paginator(Model.objects.all(),20).get_page(request.GET.get("page")),"kind":kind,"page_title":title})

@capability_required("public_content.access_management")
@require_http_methods(["GET","POST"])
def content_edit(request,kind,object_id=None):
    from django.http import Http404
    if kind not in TYPES:raise Http404
    Model,Form,title=TYPES[kind];obj=get_object_or_404(Model,pk=object_id) if object_id else None
    require(request.user,kind+(".edit" if obj else ".create"),obj)
    form=Form(request.POST if request.method=="POST" else None,actor=request.user,instance=obj)
    if request.method=="POST":
        try:
            if form.is_valid():
                obj=save_content(actor=request.user,form=form,kind=kind)
                return redirect("editorial_management:edit",kind=kind,object_id=obj.pk)
        except (ValidationError,IntegrityError) as error:
            form.add_error(None,error if isinstance(error,ValidationError) else "Ce contenu entre en conflit avec une autre modification.")
    return render(request,"espace/content_form.html",{"form":form,"kind":kind,"item":obj,"page_title":"Préparer : "+title,"gallery":obj.photos.select_related("image") if kind=="action" and obj else [],"images":PublicImage.objects.filter(approved_at__isnull=False) if kind=="action" else []})

@capability_required("public_content.access_management")
@require_http_methods(["POST"])
def transition(request,kind,object_id,operation):
    from django.http import Http404
    if kind not in TYPES:raise Http404
    obj=get_object_or_404(TYPES[kind][0],pk=object_id)
    try:
        if operation=="publish":publish_content(actor=request.user,obj=obj,kind=kind)
        else:withdraw_content(actor=request.user,obj=obj,kind=kind)
        messages.success(request,"État de publication enregistré.")
    except ValidationError as error:messages.error(request," ".join(error.messages))
    return redirect("editorial_management:edit",kind=kind,object_id=obj.pk)

@capability_required("image.manage")
@require_http_methods(["GET","POST"])
def image_upload(request):
    form=ImageForm(request.POST if request.method=="POST" else None,request.FILES or None)
    if request.method=="POST" and form.is_valid():
        try:
            upload_image(actor=request.user,upload=form.cleaned_data["photo"],alt=form.cleaned_data["alt"],source=form.cleaned_data["source"],approved=form.cleaned_data["approved"])
            messages.success(request,"Image validée et disponible pour un contenu.");return redirect("editorial_management:dashboard")
        except ValidationError as error:form.add_error("photo",error)
    return render(request,"espace/editorial_form.html",{"form":form,"page_title":"Image publique autorisée","multipart":True})

@capability_required("action.edit")
@require_http_methods(["POST"])
def gallery(request,object_id):
    with transaction.atomic():
        obj=get_object_or_404(Action.objects.select_for_update(),pk=object_id);require(request.user,"action.edit",obj)
        from django.http import Http404
        from uuid import UUID
        try:
            if request.POST.get("remove"):int(request.POST["remove"])
            else:UUID(request.POST.get("image", ""))
        except (ValueError,TypeError):raise Http404
        if request.POST.get("remove"):
            get_object_or_404(ActionPhoto,pk=request.POST["remove"],action=obj).delete()
        else:
            image=get_object_or_404(PublicImage,pk=request.POST.get("image"),approved_at__isnull=False)
            from django.db.models import Max
            position=(obj.photos.aggregate(p=Max("position"))["p"] or 0)+1
            ActionPhoto.objects.get_or_create(action=obj,image=image,defaults={"position":position,"caption":request.POST.get("caption","")[:300]})
        obj.status="DRAFT";obj.save(update_fields=["status","updated_at"]);audit(request.user,"action.gallery_changed",obj)
    return redirect("editorial_management:edit",kind="action",object_id=obj.pk)

@capability_required("editorial.manage")
@require_http_methods(["GET","POST"])
def editorial_edit(request,section=None,metric_id=None,kind="section"):
    if kind=="identity":obj=ClubIdentity.objects.first();Form=IdentityForm
    elif kind=="metric":obj=get_object_or_404(ImpactMetric,pk=metric_id) if metric_id else None;Form=MetricForm
    else:obj=EditorialSection.objects.filter(pk=section).first();Form=SectionForm
    form=Form(request.POST if request.method=="POST" else None,instance=obj)
    if obj and kind=="section":form.fields["key"].disabled=True
    if request.method=="POST" and form.is_valid():
        with transaction.atomic():
            require(request.user,"editorial.manage")
            obj=form.save(commit=False);obj.updated_by=request.user
            obj.validated_at=timezone.now() if form.cleaned_data["validated"] else None
            obj.full_clean();obj.save();audit(request.user,"editorial.updated",obj)
        return redirect("editorial_management:dashboard")
    return render(request,"espace/editorial_form.html",{"form":form,"page_title":"Contenu institutionnel validé"})
