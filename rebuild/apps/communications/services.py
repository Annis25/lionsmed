from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.core.validators import validate_email
from apps.editorial.publication import require,audit
from apps.members.models import MembershipApplication
from .models import ContactRequest,OutboxMessage

@transaction.atomic
def submit(form):
    if not form.is_valid():raise ValidationError("Formulaire invalide.")
    Model=type(form.instance)
    defaults={key:form.cleaned_data[key] for key in form.Meta.fields}
    obj,created=Model.objects.get_or_create(submission_key=form.cleaned_data["submission_token"],defaults=defaults)
    if created:
        if isinstance(obj,MembershipApplication):
            OutboxMessage.objects.create(event_key="application:"+str(obj.pk),kind="APPLICATION",recipient=obj.email,object_id=obj.pk)
        elif settings.CONTACT_RECIPIENT:
            validate_email(settings.CONTACT_RECIPIENT)
            OutboxMessage.objects.create(event_key="contact:"+str(obj.pk),kind="CONTACT",recipient=settings.CONTACT_RECIPIENT,object_id=obj.pk)
    return obj

@transaction.atomic
def change_state(*,actor,obj,state):
    kind="application" if isinstance(obj,MembershipApplication) else "contact"
    obj=type(obj).objects.select_for_update().get(pk=obj.pk)
    require(actor,kind+".manage",obj)
    if state not in {"RECEIVED","CONTACTED","FOLLOW_UP","CLOSED"}:raise ValidationError("État invalide.")
    obj.state=state;obj.full_clean();obj.save(update_fields=["state","updated_at"])
    audit(actor,kind+".state_changed",obj)
    return obj
