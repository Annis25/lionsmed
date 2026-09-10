from django.contrib import messages
from django.shortcuts import render, redirect
from django.http import FileResponse, Http404
from django.views.decorators.http import require_http_methods, require_safe
from apps.core.permissions import capability_required, DIRECTORY_ROLES
from apps.governance.models import Role
from .selectors import own_profile, profile_data, directory_page, member_profile, own_experience
from .forms import ProfileForm, ExperienceForm
from .services import update_profile, save_experience, delete_experience
from .uploads import photo_storage
from .public_profile import public_profile_url, qr_png_bytes

@capability_required("profile.view_own")
@require_safe
def profile(request):
    p = own_profile(request.user)
    context = {"member":profile_data(request.user,p,own=True),"own":True}
    if p.public_profile_enabled and p.public_slug:
        context["public_profile_url"] = public_profile_url(p)
    return render(request,"espace/profile.html",context)

@capability_required("profile.edit_own")
@require_http_methods(["GET","POST"])
def edit_profile(request):
    p = own_profile(request.user)
    if request.method == "POST":
        form = update_profile(actor=request.user,profile=p,data=request.POST,files=request.FILES)
        if form is None:
            messages.success(request,"Votre profil a été enregistré."); return redirect("members:profile")
    else:
        initial = {key:getattr(p,key) for key in ["phone","profession","public_title","bio","public_profile_enabled"]}
        initial.update(first_name=p.user.first_name,last_name=p.user.last_name)
        form = ProfileForm(actor=request.user,profile=p,initial=initial)
    return render(request,"espace/profile_edit.html",{"form":form,"member":profile_data(request.user,p,own=True)})

@capability_required("directory.view")
@require_safe
def directory(request):
    from apps.governance.models import ClubState
    from apps.dues.selectors import dues_badges
    page_obj=directory_page(request.user,request.GET)
    state=ClubState.objects.select_related("active_year").first()
    badges=dues_badges([m["id"] for m in page_obj.object_list], state.active_year if state else None)
    for member in page_obj.object_list:
        member["dues_badge"]=badges.get(member["id"])
    return render(request,"espace/directory.html",{"page_obj":page_obj,"roles":[r for r in Role.choices if r[0] in DIRECTORY_ROLES]})

@capability_required("member.view")
@require_safe
def detail(request,user_id):
    return render(request,"espace/profile.html",{"member":profile_data(request.user,member_profile(request.user,user_id)),"own":False})

@capability_required("profile.view_own")
@require_safe
def photo(request,user_id):
    p = own_profile(request.user) if request.user.pk == user_id else member_profile(request.user,user_id)
    if not p.photo_key: raise Http404
    try: handle = photo_storage().open(p.photo_key,"rb")
    except FileNotFoundError: raise Http404
    response = FileResponse(handle,content_type="image/jpeg",filename="portrait.jpg")
    response["Cache-Control"]="private, no-store"; response["X-Robots-Tag"]="noindex"
    response["X-Content-Type-Options"]="nosniff"
    return response

@capability_required("experience.manage_own")
@require_safe
def experiences(request):
    return render(request,"espace/experiences.html",{"member":profile_data(request.user,own_profile(request.user),own=True)})

@capability_required("experience.manage_own")
@require_http_methods(["GET","POST"])
def experience_edit(request,experience_id=None):
    p=own_profile(request.user); item=own_experience(request.user,experience_id) if experience_id else None
    if request.method=="POST":
        form=save_experience(actor=request.user,profile=p,data=request.POST,experience=item)
        if form is None: return redirect("members:experiences")
    else: form=ExperienceForm(actor=request.user,profile=p,instance=item)
    return render(request,"espace/experience_form.html",{"form":form,"editing":bool(item)})

@capability_required("experience.manage_own")
@require_http_methods(["GET","POST"])
def experience_delete(request,experience_id):
    item=own_experience(request.user,experience_id)
    if request.method=="POST":
        delete_experience(actor=request.user,experience=item);return redirect("members:experiences")
    return render(request,"espace/experience_delete.html",{"experience":item})

@capability_required("profile.view_own")
@require_safe
def email_information(request):
    return render(request,"espace/email_information.html")

@capability_required("profile.view_own")
@require_safe
def public_profile_qr(request):
    from django.http import HttpResponse
    p = own_profile(request.user)
    if not p.public_profile_enabled or not p.public_slug: raise Http404
    response = HttpResponse(qr_png_bytes(public_profile_url(p)), content_type="image/png")
    response["Content-Disposition"] = 'attachment; filename="profil-public-qr.png"'
    response["Cache-Control"] = "private, no-store"
    return response
