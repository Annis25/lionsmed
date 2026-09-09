from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_safe, require_http_methods
from apps.core.permissions import capability_required, can, effective_role
from apps.members.selectors import directory_page, member_profile, profile_data
from apps.members.models import MemberProfile
from .models import Role, LionsYear, ClubState
from .forms import MemberCreateForm, RoleChangeForm, StatusChangeForm, EmailChangeForm, LionsYearForm
from .services import create_member, set_role, set_member_status, set_member_email, create_lions_year, set_active_year, set_year_archived
from apps.accounts.forms import ResetForm

def _send_activation_link(request, user):
    # Action déclenchée par un responsable authentifié, pas une soumission publique :
    # le throttle anti-abus du formulaire public ne s'applique pas ici.
    from urllib.parse import urlsplit
    from django.conf import settings
    form = ResetForm({"email": user.email})
    if form.is_valid():
        origin = urlsplit(settings.SITE_ORIGIN)
        form.save(use_https=origin.scheme == "https", domain_override=origin.netloc, request=request,
            from_email=settings.DEFAULT_FROM_EMAIL, email_template_name="emails/password_reset.txt",
            html_email_template_name="emails/password_reset.html", subject_template_name="emails/password_reset_subject.txt")

@capability_required("members.view_management")
@require_safe
def members(request):
    from apps.dues.selectors import dues_badges
    page_obj=directory_page(request.user,request.GET,management=True)
    state=ClubState.objects.select_related("active_year").first()
    badges=dues_badges([m["id"] for m in page_obj.object_list], state.active_year if state else None)
    for member in page_obj.object_list:
        member["dues_badge"]=badges.get(member["id"])
    return render(request,"espace/management_members.html",{"page_obj":page_obj,"roles":Role.choices,"statuses":MemberProfile.Status.choices,"can_manage":can(request.user,"members.manage")})

@capability_required("members.manage")
@require_http_methods(["GET", "POST"])
def member_add(request):
    form = MemberCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            user = create_member(actor=request.user, **form.cleaned_data)
            _send_activation_link(request, user)
            messages.success(request, "Compte créé. Un lien de réinitialisation vient d’être envoyé à la personne pour qu’elle choisisse son mot de passe.")
            return redirect("governance:member", user_id=user.pk)
        except ValidationError as error:
            form.add_error(None, error)
    return render(request, "espace/management_member_add.html", {"form": form})

@capability_required("members.view_management")
@require_safe
def member(request,user_id):
    target = member_profile(request.user,user_id,management=True)
    context = {"member":profile_data(request.user,target,management=True), "can_manage": can(request.user,"members.manage")}
    if context["can_manage"] and effective_role(target.user) != Role.SUPER_ADMIN:
        context.update(
            role_form=RoleChangeForm(initial={"role": effective_role(target.user)}),
            status_form=StatusChangeForm(initial={"status": target.status}),
            email_form=EmailChangeForm(initial={"email": target.user.email}),
        )
    return render(request,"espace/management_detail.html",context)

@capability_required("members.manage")
@require_http_methods(["POST"])
def member_set_role(request,user_id):
    target = member_profile(request.user,user_id,management=True)
    form = RoleChangeForm(request.POST)
    if form.is_valid():
        try:
            set_role(actor=request.user, target_user=target.user, role=form.cleaned_data["role"])
            messages.success(request, "Rôle mis à jour.")
        except (ValidationError, PermissionDenied) as error:
            messages.error(request, " ".join(error.messages) if hasattr(error,"messages") else str(error))
    return redirect("governance:member", user_id=user_id)

@capability_required("members.manage")
@require_http_methods(["POST"])
def member_set_status(request,user_id):
    target = member_profile(request.user,user_id,management=True)
    form = StatusChangeForm(request.POST)
    if form.is_valid():
        try:
            set_member_status(actor=request.user, profile=target, status=form.cleaned_data["status"])
            messages.success(request, "Statut mis à jour.")
        except (ValidationError, PermissionDenied) as error:
            messages.error(request, " ".join(error.messages) if hasattr(error,"messages") else str(error))
    return redirect("governance:member", user_id=user_id)

@capability_required("members.manage")
@require_http_methods(["POST"])
def member_set_email(request,user_id):
    target = member_profile(request.user,user_id,management=True)
    form = EmailChangeForm(request.POST)
    if form.is_valid():
        try:
            set_member_email(actor=request.user, target_user=target.user, email=form.cleaned_data["email"])
            messages.success(request, "Adresse e-mail mise à jour.")
        except (ValidationError, PermissionDenied) as error:
            messages.error(request, " ".join(error.messages) if hasattr(error,"messages") else str(error))
    return redirect("governance:member", user_id=user_id)

@capability_required("year.view")
@require_http_methods(["GET", "POST"])
def years(request):
    form = LionsYearForm(request.POST or None)
    if request.method == "POST" and can(request.user,"year.manage") and form.is_valid():
        try:
            create_lions_year(actor=request.user, start_year=form.cleaned_data["start_year"])
            messages.success(request, "Année Lions créée.")
            return redirect("governance:years")
        except ValidationError as error:
            form.add_error(None, error)
    return render(request,"espace/years.html",{"years":LionsYear.objects.all(),
        "club_state":ClubState.objects.select_related("active_year").first(),
        "form":form,"can_manage":can(request.user,"year.manage")})

@capability_required("year.manage")
@require_http_methods(["POST"])
def year_activate(request,year_id):
    from django.shortcuts import get_object_or_404
    year = get_object_or_404(LionsYear,pk=year_id)
    set_active_year(actor=request.user, lions_year=year)
    messages.success(request, "Année Lions active mise à jour.")
    return redirect("governance:years")

@capability_required("year.manage")
@require_http_methods(["POST"])
def year_archive_toggle(request,year_id):
    from django.shortcuts import get_object_or_404
    year = get_object_or_404(LionsYear,pk=year_id)
    set_year_archived(actor=request.user, lions_year=year, archived=not year.archived_at)
    messages.success(request, "Archivage mis à jour.")
    return redirect("governance:years")

@capability_required("statistics.view")
@require_safe
def statistics(request):
    from apps.agenda.models import Attendance, Event
    from apps.dues.models import DuesRecord
    from apps.documents.models import Document
    attendance_counts={row["status"]:row["total"] for row in Attendance.objects.values("status").annotate(total=Count("id"))}
    dues_counts={}
    for record in DuesRecord.objects.only("tranche1_paid","tranche2_paid"):
        dues_counts[record.status]=dues_counts.get(record.status,0)+1
    document_counts=list(Document.objects.filter(status="AVAILABLE").values("category").annotate(total=Count("id")))
    return render(request,"espace/statistics.html",{
        "attendance_counts":attendance_counts,"dues_counts":dues_counts,"document_counts":document_counts,
        "events_with_attendance":Event.objects.filter(attendances__isnull=False).distinct().count(),
    })
