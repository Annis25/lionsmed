from uuid import uuid4
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from apps.core.permissions import can
from .models import MemberProfile, AssociationExperience
from .forms import ProfileForm, ExperienceForm
from .uploads import encode_photo, photo_storage
from .public_profile import ensure_public_slug

PROFILE_FIELDS = {"phone", "profession", "public_title", "bio", "public_profile_enabled"}

def update_profile(*, actor, profile, data, files=None):
    if not can(actor, "profile.edit_own", profile): raise PermissionDenied
    form = ProfileForm(data, files, actor=actor, profile=profile)
    if not form.is_valid(): return form
    clean = form.cleaned_data
    encoded = None
    if clean.get("photo"):
        try: encoded = encode_photo(clean["photo"])
        except ValidationError as error:
            form.add_error("photo", error); return form
    storage = photo_storage(); new_key = None
    try:
        # Le service possède sa transaction : pas de fichier publié avant commit externe.
        with transaction.atomic(durable=True):
            user = get_user_model().objects.select_for_update().get(pk=actor.pk)
            current = MemberProfile.objects.select_for_update().get(pk=profile.pk)
            if not can(user, "profile.edit_own", current): raise PermissionDenied
            user.first_name = clean["first_name"]; user.last_name = clean["last_name"]
            user.save(update_fields=["first_name", "last_name", "updated_at"])
            for field in PROFILE_FIELDS: setattr(current, field, clean[field])
            if current.public_profile_enabled: ensure_public_slug(current)
            old_key = current.photo_key
            if encoded is not None:
                new_key = storage.save("portraits/" + uuid4().hex + ".jpg", encoded)
                current.photo_key = new_key
            elif clean["remove_photo"]: current.photo_key = ""
            current.full_clean(); current.save()
            if old_key and old_key != current.photo_key:
                transaction.on_commit(lambda: storage.delete(old_key), robust=True)
    except Exception:
        if new_key: storage.delete(new_key)
        raise
    return None

@transaction.atomic
def save_experience(*, actor, profile, data, experience=None):
    actor = get_user_model().objects.select_for_update().get(pk=actor.pk)
    if not can(actor, "experience.manage_own", profile): raise PermissionDenied
    if experience:
        experience = AssociationExperience.objects.select_for_update().get(pk=experience.pk)
    if not can(actor, "experience.manage_own", experience or profile): raise PermissionDenied
    form = ExperienceForm(data, actor=actor, profile=profile, instance=experience)
    if not form.is_valid(): return form
    form.save(); return None

@transaction.atomic
def delete_experience(*, actor, experience):
    actor = get_user_model().objects.select_for_update().get(pk=actor.pk)
    current = AssociationExperience.objects.select_for_update().get(pk=experience.pk)
    if not can(actor, "experience.manage_own", current): raise PermissionDenied
    current.delete()
