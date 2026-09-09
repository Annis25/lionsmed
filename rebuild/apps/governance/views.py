from django.shortcuts import render
from django.views.decorators.http import require_safe
from apps.core.permissions import capability_required
from apps.members.selectors import directory_page, member_profile, profile_data, scoped_profiles
from apps.members.models import MemberProfile
from .models import Role, LionsYear, ClubState, Mandate

@capability_required("members.view_management")
@require_safe
def members(request):
    return render(request,"espace/management_members.html",{"page_obj":directory_page(request.user,request.GET,management=True),"roles":Role.choices,"statuses":MemberProfile.Status.choices})

@capability_required("members.view_management")
@require_safe
def member(request,user_id):
    return render(request,"espace/management_detail.html",{"member":profile_data(request.user,member_profile(request.user,user_id,management=True),management=True)})

@capability_required("year.view")
@require_safe
def years(request):
    return render(request,"espace/years.html",{"years":LionsYear.objects.all(),"club_state":ClubState.objects.select_related("active_year").first()})

@capability_required("management.access")
@require_safe
def dashboard(request):
    qs=scoped_profiles(request.user,management=True)
    return render(request,"espace/management_dashboard.html",{"member_count":qs.count(),"active_count":qs.filter(status="ACTIVE",user__is_active=True).count(),
        "mandate_count":Mandate.objects.count(),"club_state":ClubState.objects.select_related("active_year").first()})
