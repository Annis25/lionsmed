from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_safe, require_http_methods
from apps.core.permissions import capability_required, can, effective_role
from apps.members.selectors import directory_page, member_profile, profile_data
from apps.members.models import MemberProfile
from .models import Role, LionsYear, ClubState, Mandate
from .forms import MemberCreateForm, RoleChangeForm, StatusChangeForm, EmailChangeForm, LionsYearForm, MandateForm
from .mandates import save_mandate, end_mandate, delete_mandate
from .selectors import year_mandates, public_bureau, reference_year
from .services import create_member, resend_member_invitation, set_role, set_member_status, set_member_email, create_lions_year, set_active_year, set_year_archived

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
            messages.success(request, "Compte créé. Une invitation sécurisée a été placée dans la file d’envoi pour que la personne choisisse son mot de passe.")
            return redirect("governance:member", user_id=user.pk)
        except ValidationError as error:
            form.add_error(None, error)
    return render(request, "espace/management_member_add.html", {"form": form})

@capability_required("members.view_management")
@require_safe
def member(request,user_id):
    target = member_profile(request.user,user_id,management=True)
    context = {
        "member": profile_data(request.user, target, management=True),
        "can_manage": can(request.user, "members.manage"),
        "can_resend_invitation": can(request.user, "members.manage") and not target.user.has_usable_password(),
        "can_manage_mandates": can(request.user, "mandate.manage"),
    }
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


@capability_required("members.manage")
@require_http_methods(["POST"])
def member_resend_invitation(request, user_id):
    target = member_profile(request.user, user_id, management=True)
    if request.POST.get("confirmed") != "yes":
        messages.error(request, "Veuillez confirmer le renvoi de l’invitation.")
        return redirect("governance:member", user_id=user_id)
    try:
        resend_member_invitation(actor=request.user, target_user=target.user)
        messages.success(request, "Une nouvelle invitation sécurisée a été placée dans la file d’envoi.")
    except (ValidationError, PermissionDenied) as error:
        messages.error(request, " ".join(error.messages) if hasattr(error, "messages") else str(error))
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

def _error_text(error):
    return " ".join(error.messages) if hasattr(error, "messages") else str(error)


@capability_required("members.view_management")
@require_safe
def mandates(request):
    """Bureau et mandats : mandats d'une Année Lions (l'année active par défaut) et aperçu
    exact de ce que publie « Notre bureau » — même sélecteur que la page publique."""
    from django.shortcuts import get_object_or_404
    active = reference_year()
    year = get_object_or_404(LionsYear, pk=request.GET["annee"]) if request.GET.get("annee", "").isdigit() else active
    return render(request, "espace/mandates.html", {
        "year": year, "active_year": active, "years": LionsYear.objects.all(),
        "rows": year_mandates(request.user, year) if year else [],
        "public": public_bureau() if year and active and year.pk == active.pk else None,
        "can_manage": can(request.user, "mandate.manage"),
    })


@capability_required("mandate.manage")
@require_http_methods(["GET", "POST"])
def mandate_edit(request, mandate_id=None):
    from django.shortcuts import get_object_or_404
    mandate = get_object_or_404(Mandate, pk=mandate_id) if mandate_id else None
    member_id = request.GET.get("membre") if not mandate else None
    form = MandateForm(request.POST or None, mandate=mandate, default_year=reference_year(),
        default_profile_id=MemberProfile.objects.filter(user_id=member_id).values_list("pk", flat=True).first() if member_id else None)
    if request.method == "POST" and form.is_valid():
        try:
            saved = save_mandate(actor=request.user, data=form.mandate_data(), mandate=mandate)
            messages.success(request, "Mandat enregistré." + (" Il apparaît dans « Notre bureau »." if saved.validated_at and saved.public_authorized else ""))
            return redirect(f"{reverse('governance:mandates')}?annee={saved.lions_year_id}")
        except ValidationError as error:
            form.add_error(None, error)
    return render(request, "espace/mandate_form.html", {"form": form, "mandate": mandate})


@capability_required("mandate.manage")
@require_http_methods(["POST"])
def mandate_end(request, mandate_id):
    from django.shortcuts import get_object_or_404
    mandate = get_object_or_404(Mandate, pk=mandate_id)
    try:
        end_mandate(actor=request.user, mandate=mandate)
        messages.success(request, "Mandat terminé à la date du jour ; il reste dans l’historique.")
    except (ValidationError, PermissionDenied) as error:
        messages.error(request, _error_text(error))
    return redirect(f"{reverse('governance:mandates')}?annee={mandate.lions_year_id}")


@capability_required("mandate.manage")
@require_http_methods(["GET", "POST"])
def mandate_delete(request, mandate_id):
    from django.shortcuts import get_object_or_404
    mandate = get_object_or_404(Mandate.objects.select_related("profile__user", "lions_year"), pk=mandate_id)
    if request.method == "POST":
        year_id = mandate.lions_year_id
        delete_mandate(actor=request.user, mandate=mandate)
        messages.success(request, "Mandat supprimé.")
        return redirect(f"{reverse('governance:mandates')}?annee={year_id}")
    return render(request, "espace/mandate_delete.html", {"mandate": mandate,
        "member_name": mandate.profile.user.get_full_name() or "Membre"})


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
