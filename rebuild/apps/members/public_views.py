from django.http import Http404, FileResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_safe
from django.conf import settings
from apps.editorial.seo import metadata
from apps.editorial import identity
from .models import MemberProfile
from .uploads import photo_storage
from .public_profile import public_profile_url


def _public_profile_or_404(slug):
    profile = MemberProfile.objects.select_related("user").filter(public_slug=slug, public_profile_enabled=True).first()
    if not profile or not profile.user.is_active:
        raise Http404
    return profile


@require_safe
def detail(request, slug):
    profile = _public_profile_or_404(slug)
    name = profile.user.get_full_name() or "Membre"
    title = f"{name} | {identity.NAME}"
    role_label = profile.public_title or "membre"
    description = (profile.bio or f"{name}, {role_label} du {identity.NAME}.")[:300]
    person = {"@type": "Person", "name": name, "memberOf": {"@type": "Organization", "name": identity.NAME}}
    if profile.public_title: person["jobTitle"] = profile.public_title
    if profile.photo_key: person["image"] = settings.SITE_ORIGIN + f"/membres/{slug}/photo/"
    context = metadata(request, title=title, description=description, schema=person,
        parents=({"name": "Notre Club", "url": "/notre-club/"},))
    context.update(page_title=name, lede=profile.bio,
        member=profile, name=name,
        experiences=profile.experiences.all().order_by("-start_year"),
        mandates=profile.mandates.filter(validated_at__isnull=False, public_authorized=True).select_related("lions_year"),
        photo_url=(f"/membres/{slug}/photo/" if profile.photo_key else None))
    return render(request, "public/member_profile.html", context)


@require_safe
def photo(request, slug):
    profile = _public_profile_or_404(slug)
    if not profile.photo_key: raise Http404
    try: handle = photo_storage().open(profile.photo_key, "rb")
    except FileNotFoundError: raise Http404
    response = FileResponse(handle, content_type="image/jpeg")
    response["Cache-Control"] = "public, max-age=3600"
    response["X-Content-Type-Options"] = "nosniff"
    return response
