from django.conf import settings
from django.http import Http404,HttpResponse,FileResponse,HttpResponsePermanentRedirect
from django.shortcuts import render,get_object_or_404
from django.core.paginator import Paginator
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_safe
from apps.service_actions.models import Action,Axis
from apps.agenda.models import Event
from apps.governance.models import Mandate
from apps.core.models import PublicImage
from .models import EditorialSection,ImpactMetric,Redirect
from .selectors import public_qs,sections,institution,image_is_public
from .seo import metadata
from .images import storage
from . import identity

PAGE_INFO={"club":("Notre Club","Ancrés à Sfax, unis par une même volonté : servir."),"join":("Nous rejoindre","Rejoindre notre club, c’est choisir de servir, d’agir et de grandir avec d’autres."),"legal":("Mentions légales","Informations institutionnelles et mentions de publication."),"privacy":("Confidentialité","Comment nous utilisons les informations que vous nous confiez."),"sitemap":("Plan du site","Les pages publiques du Lions Club Sfax-Méditerranée.")}

def public_context(request,title,description,**kwargs):
    axis_content=sections()
    context={"institution":institution(),"page_title":title,"lede":description,"axes":Axis.choices,
        "axis_sections":[{"value":value,"label":label,"section":axis_content.get("axis_"+value.lower()),
            "default_body":identity.AXES_DEFAULT_BODY.get(value)} for value,label in Axis.choices],
        "axes_intro":identity.AXES_INTRO,"causes_lions":identity.CAUSES_LIONS}
    context.update(metadata(request,title=title,description=description,**kwargs));return context

@require_safe
def home(request):
    info=institution()
    schema={"@type":"NGO","@id":settings.SITE_ORIGIN+"/#organisation","name":info["name"],"url":settings.SITE_ORIGIN+"/","slogan":info["motto"],"address":{"@type":"PostalAddress","addressLocality":info["city"],"addressCountry":"TN"},"memberOf":{"@type":"Organization","name":info["affiliation"]}}
    if info["email"]:schema["email"]=info["email"]
    context=public_context(request,identity.NAME,"Depuis Sfax, nous servons. Nos quatre priorités : diabète, environnement, humanitaire et jeunesse.",schema=schema)
    context["page_css"]="css/accueil.css"
    context.update(actions=public_qs(Action).order_by("-performed_on","id")[:3],events=public_qs(Event).filter(starts_at__gte=timezone.now()).order_by("starts_at")[:2],sections=sections(),metrics=ImpactMetric.objects.filter(validated_at__isnull=False))
    return render(request,"public/home.html",context)

@require_safe
def page(request,page):
    title,description=PAGE_INFO[page];content=sections()
    context=public_context(request,title,description,indexable=page not in {"legal","privacy"} or page in content)
    context.update(sections=content,page_kind=page,page_css={"club":"css/notre-club.css","join":"css/rejoindre.css"}.get(page))
    if page=="club":
        context["valeurs"]=identity.VALEURS
        today=timezone.localdate()
        context["bureau"]=[{"name":m.profile.user.get_full_name(),"function":m.function,"year":m.lions_year.label} for m in Mandate.objects.filter(validated_at__isnull=False,public_authorized=True,starts_on__lte=today,ends_on__gt=today,profile__user__is_active=True).select_related("profile__user","lions_year") if m.profile.user.get_full_name()]
    return render(request,"public/"+page+".html",context)

@require_safe
def listing(request,kind):
    model,title,description,route={"action":(Action,"Nos Actions","Le service prend tout son sens lorsqu’il devient action.","actions:list"),"event":(Event,"Événements","Nos rendez-vous et rencontres publics.","agenda:list")}[kind]
    if kind=="event" and not public_qs(model).exists():raise Http404
    qs=public_qs(model)
    if kind=="action":
        if request.GET.get("axis") in Axis.values:qs=qs.filter(axis=request.GET["axis"])
        qs=qs.order_by("-performed_on","id")
    if kind=="event":
        qs=qs.filter(ends_at__lt=timezone.now()) if request.GET.get("archive")=="1" else qs.filter(ends_at__gte=timezone.now())
        qs=qs.order_by("starts_at","id")
    if request.GET.get("q"):qs=qs.filter(title__icontains=request.GET["q"][:100])
    context=public_context(request,title,description)
    context["page_css"]="css/nos-actions.css" if kind=="action" else None
    context.update(page_obj=Paginator(qs,9).get_page(request.GET.get("page")),kind=kind)
    return render(request,"public/list.html",context)

@require_safe
def detail(request,slug,kind):
    model,title,route={"action":(Action,"Nos Actions","actions:list"),"event":(Event,"Événements","agenda:list")}[kind]
    obj=public_qs(model).filter(slug=slug).first()
    if not obj:
        redirection=Redirect.objects.filter(old_path=request.path).first()
        if redirection:
            try:redirection.full_clean()
            except Exception:raise Http404
            for model in (Action, Event):
                target=public_qs(model).filter(slug=redirection.new_path.rstrip('/').split('/')[-1]).first()
                if target and target.get_absolute_url()==redirection.new_path:
                    return HttpResponsePermanentRedirect(redirection.new_path)
        raise Http404
    schema=None
    if kind=="event" and obj.starts_at and obj.ends_at and obj.location:
        schema={"@type":"Event","name":obj.title,"description":obj.summary,"startDate":obj.starts_at.isoformat(),"endDate":obj.ends_at.isoformat(),"location":{"@type":"Place","name":obj.location},"eventStatus":"https://schema.org/EventScheduled","url":settings.SITE_ORIGIN+obj.get_absolute_url()}
    if schema and obj.cover and obj.cover.approved_at:schema["image"]=settings.SITE_ORIGIN+obj.cover.get_absolute_url()
    context=public_context(request,obj.meta_title or obj.title,obj.meta_description or obj.summary,schema=schema,image=obj.social_image or obj.cover,parents=({"name":title,"url":reverse(route)},))
    context.update(item=obj,page_title=obj.title,lede=obj.summary,kind=kind,list_url=reverse(route))
    if kind=="action":context["photos"]=obj.photos.filter(image__approved_at__isnull=False).select_related("image")
    return render(request,"public/detail.html",context)

@require_safe
def image(request,image_id,size):
    item=get_object_or_404(PublicImage,pk=image_id)
    if size not in {480,1024} or not image_is_public(item):raise Http404
    try:handle=storage().open(item.small_key if size==480 else item.large_key,"rb")
    except FileNotFoundError:raise Http404
    return FileResponse(handle,content_type="image/webp")

@require_safe
def robots(request):
    text="User-agent: *\nAllow: /\nSitemap: "+settings.SITE_ORIGIN+"/sitemap.xml\n" if settings.PUBLIC_INDEXING_ENABLED else "User-agent: *\nDisallow: /\n"
    return HttpResponse(text,content_type="text/plain")
