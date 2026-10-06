from django.http import FileResponse,Http404
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
from .images import upload_image,storage
from apps.core.image_processing import MAX_BYTES

TYPES={"action":(Action,ActionForm,"Actions"),"event":(Event,EventForm,"Événements")}

@capability_required("public_content.access_management")
@require_safe
def dashboard(request):
    return render(request,"espace/public_content.html",{
        "sections": EditorialSection.objects.all(),
        "metrics": ImpactMetric.objects.all(),
        "can_application_requests": can(request.user, "application.view"),
        "can_contact_requests": can(request.user, "contact.view"),
    })

@capability_required("public_content.access_management")
@require_safe
def content_list(request,kind):
    if kind not in TYPES:raise Http404
    Model,Form,title=TYPES[kind];require(request.user,kind+".edit")
    queryset=Model.objects.select_related("cover") if kind=="action" else Model.objects.all()
    template="espace/action_management_list.html" if kind=="action" else "espace/content_list.html"
    return render(request,template,{"page_obj":Paginator(queryset,20).get_page(request.GET.get("page")),"kind":kind,"page_title":title})

ACTION_IMAGE_SOURCE="Photo fournie par le Lions Club Sfax-Méditerranée"

def _store_action_images(actor,obj,cleaned):
    """Dépose les images choisies ; une image refusée n'empêche pas les autres et laisse l'action intacte."""
    added=0;refused=[]
    uploads=[(True,cleaned.get("main_image_upload"))]+[(False,upload) for upload in cleaned.get("gallery_uploads",[])]
    for is_cover,upload in uploads:
        if not upload:continue
        try:
            image=upload_image(actor=actor,upload=upload,alt="Image de l’action : "+obj.title,source=ACTION_IMAGE_SOURCE,approved=True)
            if is_cover:
                obj.cover=image;obj.save(update_fields=["cover","updated_at"])
            else:
                with transaction.atomic():
                    position=(obj.photos.order_by("-position").values_list("position",flat=True).first() or 0)+1
                    ActionPhoto.objects.create(action=obj,image=image,position=position)
        except ValidationError as error:
            refused.append("« "+upload.name+" » : "+" ".join(error.messages));continue
        except IntegrityError:
            refused.append("« "+upload.name+" » : l’enregistrement a échoué, déposez-la de nouveau.");continue
        added+=1
    return added,refused

def _save_action(request,form,*,was_published):
    """Enregistre, dépose les images, publie si demandé. Une fois l'action enregistrée, tout
    refus (image, publication) est rapporté sur sa page de modification : jamais de brouillon
    caché derrière un formulaire de création réaffiché."""
    intent=request.POST.get("intent","draft")
    obj=save_content(actor=request.user,form=form,kind="action",keep_published=was_published and intent=="update")
    added,refused=_store_action_images(request.user,obj,form.cleaned_data)
    blocked=""
    if intent=="publish":
        if refused:blocked="Une image a été refusée."
        else:
            try:publish_content(actor=request.user,obj=obj,kind="action")
            except ValidationError as error:blocked=" ".join(error.messages)
    images=" "+("1 image ajoutée." if added==1 else f"{added} images ajoutées.") if added else ""
    if intent=="publish" and not blocked:messages.success(request,"Action publiée. Elle est visible sur le site public."+images)
    elif intent=="publish":messages.error(request,"Votre action est enregistrée en brouillon, mais elle n’est pas encore publiée. "+blocked)
    elif obj.status=="PUBLISHED":messages.success(request,"Modifications enregistrées. L’action reste publiée."+images)
    else:messages.success(request,"Brouillon enregistré. L’action n’est pas visible sur le site public."+images)
    if blocked and images:messages.info(request,images.strip())
    for line in refused:messages.error(request,"Image non ajoutée — "+line)
    return obj

@capability_required("public_content.access_management")
@require_http_methods(["GET","POST"])
def content_edit(request,kind,object_id=None):
    if kind not in TYPES:raise Http404
    Model,Form,title=TYPES[kind];obj=get_object_or_404(Model,pk=object_id) if object_id else None
    require(request.user,kind+(".edit" if obj else ".create"),obj)
    was_published=bool(obj and obj.status=="PUBLISHED")
    form=Form(
        request.POST if request.method=="POST" else None,
        request.FILES if request.method=="POST" else None,
        actor=request.user,
        instance=obj,
    )
    if request.method=="POST":
        try:
            if form.is_valid():
                if kind=="action":saved=_save_action(request,form,was_published=was_published)
                else:saved=save_content(actor=request.user,form=form,kind=kind)
                return redirect("editorial_management:edit",kind=kind,object_id=saved.pk)
        except (ValidationError,IntegrityError) as error:
            form.add_error(None,error if isinstance(error,ValidationError) else "Ce contenu entre en conflit avec une autre modification.")
    if kind!="action":
        return render(request,"espace/content_form.html",{"form":form,"kind":kind,"item":obj,"page_title":"Préparer : "+title})
    return render(request,"espace/action_form.html",{
        "form":form,"kind":kind,"item":obj,"page_title":"Modifier l’action" if obj else "Nouvelle action",
        "gallery":obj.photos.select_related("image") if obj else [],
        "photo_max_bytes":MAX_BYTES,
    })

TRANSITION_DONE={
    ("action","publish"):"Action publiée. Elle est visible sur le site public.",
    ("action","draft"):"Action remise en brouillon. Elle n’est plus visible sur le site public.",
    ("action","withdraw"):"Action retirée du site public.",
    ("event","publish"):"Événement publié.",
    ("event","withdraw"):"Événement retiré.",
}

@capability_required("public_content.access_management")
@require_http_methods(["POST"])
def transition(request,kind,object_id,operation):
    if kind not in TYPES:raise Http404
    obj=get_object_or_404(TYPES[kind][0],pk=object_id)
    try:
        if operation=="publish":publish_content(actor=request.user,obj=obj,kind=kind)
        elif operation=="draft":
            require(request.user,kind+".publish",obj);obj.status="DRAFT";obj.save(update_fields=["status","updated_at"]);audit(request.user,kind+".drafted",obj)
        else:withdraw_content(actor=request.user,obj=obj,kind=kind)
        messages.success(request,TRANSITION_DONE.get((kind,operation),"État de publication enregistré."))
    except ValidationError as error:messages.error(request,"Publication impossible : "+" ".join(error.messages))
    return redirect("editorial_management:edit",kind=kind,object_id=obj.pk)

@capability_required("action.edit")
@require_http_methods(["POST"])
def action_delete(request,object_id):
    if request.POST.get("confirmed")!="yes":
        # Sans la case cochée (JavaScript coupé, requête forgée), rien n'est supprimé.
        obj=get_object_or_404(Action,pk=object_id);require(request.user,"action.edit",obj)
        messages.error(request,"Suppression non confirmée : cochez la case de confirmation avant de supprimer.")
        return redirect("editorial_management:edit",kind="action",object_id=obj.pk)
    with transaction.atomic():
        obj=get_object_or_404(Action.objects.select_for_update(),pk=object_id);require(request.user,"action.edit",obj)
        obj.photos.all().delete();audit(request.user,"action.deleted",obj);obj.delete()
    messages.success(request,"Action supprimée définitivement.")
    return redirect("editorial_management:list",kind="action")

@capability_required("public_content.access_management")
@require_safe
def image_preview(request,image_id,size):
    """Aperçu réservé à l'espace de gestion : la route publique `editorial:image` ne sert une
    image que lorsqu'elle illustre un contenu publié, donc jamais celles d'un brouillon."""
    item=get_object_or_404(PublicImage,pk=image_id)
    if size not in {480,1024}:raise Http404
    try:handle=storage().open(item.small_key if size==480 else item.large_key,"rb")
    except FileNotFoundError:raise Http404
    return FileResponse(handle,content_type="image/webp")

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
    from uuid import UUID
    with transaction.atomic():
        obj=get_object_or_404(Action.objects.select_for_update(),pk=object_id);require(request.user,"action.edit",obj)
        try:
            if request.POST.get("remove"):int(request.POST["remove"])
            else:UUID(request.POST.get("image", ""))
        except (ValueError,TypeError):raise Http404
        if request.POST.get("remove"):
            get_object_or_404(ActionPhoto,pk=request.POST["remove"],action=obj).delete()
            done="Image retirée."
        else:
            if obj.photos.count() >= 9:
                messages.error(request, "Une action peut avoir au plus neuf images supplémentaires, en plus de l’image principale.")
                return redirect("editorial_management:edit",kind="action",object_id=obj.pk)
            image=get_object_or_404(PublicImage,pk=request.POST.get("image"),approved_at__isnull=False)
            from django.db.models import Max
            position=(obj.photos.aggregate(p=Max("position"))["p"] or 0)+1
            ActionPhoto.objects.get_or_create(action=obj,image=image,defaults={"position":position,"caption":request.POST.get("caption","")[:300]})
            done="Image ajoutée."
        # Une galerie ne contient que des images autorisées : la modifier ne remet pas en cause
        # la publication (même règle que le bouton « Modifier » d'une action publiée).
        obj.save(update_fields=["updated_at"]);audit(request.user,"action.gallery_changed",obj)
    messages.success(request,done+(" L’action reste publiée." if obj.status=="PUBLISHED" else ""))
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
