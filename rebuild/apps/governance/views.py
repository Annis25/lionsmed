from django.db.models import Count
from django.shortcuts import render
from django.utils import timezone
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
    from apps.dues.models import DuesRecord
    from apps.agenda.models import Event
    from apps.documents.models import Document
    qs=scoped_profiles(request.user,management=True)
    club_state=ClubState.objects.select_related("active_year").first()
    to_regularize=DuesRecord.objects.filter(status="TO_REGULARIZE",lions_year=club_state.active_year).count() if club_state and club_state.active_year else 0
    return render(request,"espace/management_dashboard.html",{"member_count":qs.count(),"active_count":qs.filter(status="ACTIVE",user__is_active=True).count(),
        "mandate_count":Mandate.objects.count(),"club_state":club_state,"to_regularize":to_regularize,
        "upcoming_events_count":Event.objects.filter(status="PUBLISHED",starts_at__gte=timezone.now()).count(),
        "document_count":Document.objects.filter(status="AVAILABLE").count()})


@capability_required("statistics.view")
@require_safe
def statistics(request):
    from apps.agenda.models import Attendance, Event
    from apps.dues.models import DuesRecord
    from apps.documents.models import Document
    attendance_counts={row["status"]:row["total"] for row in Attendance.objects.values("status").annotate(total=Count("id"))}
    dues_counts={row["status"]:row["total"] for row in DuesRecord.objects.values("status").annotate(total=Count("id"))}
    document_counts=list(Document.objects.filter(status="AVAILABLE").values("category").annotate(total=Count("id")))
    return render(request,"espace/statistics.html",{
        "attendance_counts":attendance_counts,"dues_counts":dues_counts,"document_counts":document_counts,
        "events_with_attendance":Event.objects.filter(attendances__isnull=False).distinct().count(),
    })
