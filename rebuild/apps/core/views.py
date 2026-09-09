from django.http import HttpResponse
from django.shortcuts import render
from apps.governance.models import ClubState, Role
from .permissions import capability_required, effective_role
from apps.members.selectors import own_profile, profile_data


def home(request):
    return render(request, "public/home.html")


@capability_required("account.access_private_area")
def dashboard(request):
    state = ClubState.objects.select_related("active_year").first()
    role = effective_role(request.user)
    return render(request, "espace/dashboard.html", {
        "effective_role_label": Role(role).label,
        "member": profile_data(request.user, own_profile(request.user), own=True),
        "active_year": state.active_year if state else None,
    })


def robots(request):
    return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")
