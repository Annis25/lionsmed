from django.conf import settings
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import transaction
from django.core.validators import validate_email
from apps.core.permissions import can
from apps.editorial.publication import require,audit
from apps.members.models import MembershipApplication
from .models import ContactRequest,OutboxMessage,Notification

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

@transaction.atomic
def notify(*,recipient,category,title,event_key,excerpt="",target_kind="",target_id="",email=False,outbox_kind=None):
    """Intention in-app idempotente ; e-mail facultatif réutilisant l'outbox existante, jamais une file séparée."""
    if category not in Notification.Category.values:raise ValidationError("Catégorie de notification invalide.")
    notification,created=Notification.objects.get_or_create(event_key=event_key,defaults={
        "recipient":recipient,"category":category,"title":title[:180],"excerpt":excerpt[:300],
        "target_kind":target_kind[:20],"target_id":str(target_id)[:64]})
    if created and email and recipient.email:
        kind=outbox_kind or {"IMPORTANT":"IMPORTANT","EVENT":"EVENT_REMINDER","DOCUMENT":"DOCUMENT"}.get(category)
        if kind:OutboxMessage.objects.get_or_create(event_key="outbox:"+event_key,defaults={
            "kind":kind,"recipient":recipient.email,"object_id":notification.pk})
    return notification

@transaction.atomic
def send_important_notification(*,actor,recipient,title,excerpt):
    if not can(actor,"notification.send"):raise PermissionDenied
    import uuid
    notification=notify(recipient=recipient,category="IMPORTANT",title=title,excerpt=excerpt,
        event_key=f"important:{uuid.uuid4()}",target_kind="",target_id="",email=True)
    audit(actor,"notification.sent",notification)
    return notification
