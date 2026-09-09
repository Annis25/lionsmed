import json
from django.conf import settings
from django.urls import reverse
from django.templatetags.static import static
from . import identity

def metadata(request,*,title,description,path=None,indexable=True,image=None,schema=None,parents=()):
    path=path or request.path
    if request.GET.get("page", "").isdigit() and int(request.GET["page"])>1:path+="?page="+str(int(request.GET["page"]))
    filtered=any(request.GET.get(k) for k in ["axis","q","category","archive"])
    indexable=bool(indexable and not filtered and settings.PUBLIC_INDEXING_ENABLED)
    request.public_indexable=indexable
    canonical=settings.SITE_ORIGIN+path
    title=title+" — "+identity.NAME if title!=identity.NAME else title
    crumbs=[{"name":"Accueil","url":reverse("core:home")}]+list(parents)
    if request.path!="/":crumbs.append({"name":title.split(" — ")[0],"url":request.path})
    graph=[]
    if request.path!="/":graph.append({"@type":"BreadcrumbList","itemListElement":[{"@type":"ListItem","position":i+1,"name":c["name"],"item":settings.SITE_ORIGIN+c["url"]} for i,c in enumerate(crumbs)]})
    if schema:graph.append(schema)
    raw=json.dumps({"@context":"https://schema.org","@graph":graph},ensure_ascii=False)
    raw=raw.replace("<",r"\u003C").replace(">",r"\u003E").replace("&",r"\u0026")
    return {"seo_title":title,"seo_description":description[:300],"canonical_url":canonical,"seo_robots":"index, follow" if indexable else "noindex, follow", "seo_image":settings.SITE_ORIGIN+(image.get_absolute_url() if image and image.approved_at else static("images/emblem-256.png")),"structured_json":raw,"breadcrumbs":crumbs}
