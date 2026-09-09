from django.contrib import messages
from django.shortcuts import render, redirect
from django.http import FileResponse, Http404
from django.views.decorators.http import require_http_methods, require_safe
from apps.core.permissions import capability_required, can
from apps.governance.models import Role
from .selectors import own_profile, profile_data, directory_page, member_profile, own_experience
from .forms import ProfileForm, ExperienceForm, VISIBILITY
from .services import update_profile, save_experience, delete_experience
from .uploads import photo_storage

@capability_required("profile.view_own")
@require_safe
def profile(request):
    return render(request,"espace/profile.html",{"member":profile_data(request.user,own_profile(request.user),own=True),"own":True})

@capability_required("profile.edit_own")
@require_http_methods(["GET","POST"])
def edit_profile(request):
    p = own_profile(request.user)
    if request.method == "POST":
        form = update_profile(actor=request.user,profile=p,data=request.POST,files=request.FILES)
        if form is None:
            messages.success(request,"Votre profil a été enregistré."); return redirect("members:profile")
    else:
        initial = {key:getattr(p,key) for key in ["phone","profession","bio",*VISIBILITY]}
        initial.update(first_name=p.user.first_name,last_name=p.user.last_name)
        form = ProfileForm(actor=request.user,profile=p,initial=initial)
    return render(request,"espace/profile_edit.html",{"form":form,"member":profile_data(request.user,p,own=True)})

@capability_required("directory.view")
@require_safe
def directory(request):
    return render(request,"espace/directory.html",{"page_obj":directory_page(request.user,request.GET),"roles":[r for r in Role.choices if r[0]!="INVITE"]})

@capability_required("member.view")
@require_safe
def detail(request,user_id):
    return render(request,"espace/profile.html",{"member":profile_data(request.user,member_profile(request.user,user_id)),"own":False})

@capability_required("profile.view_own")
@require_safe
def photo(request,user_id):
    p = own_profile(request.user) if request.user.pk == user_id else member_profile(request.user,user_id)
    if not p.photo_key or (request.user.pk != user_id and not p.share_photo): raise Http404
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
