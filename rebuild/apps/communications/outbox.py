from datetime import timedelta
from uuid import uuid4
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.core.mail import EmailMultiAlternatives
from .models import OutboxMessage, Notification, MemberEmailCampaign
from .emailing import render_transactional, render_broadcast, recipient_for_email
from .services import refresh_campaign_status


def _mail_parts(item):
    """Construit uniquement le contexte permis au destinataire de l'outbox."""
    user = recipient_for_email(item.recipient)
    if item.kind == "MEMBER_BROADCAST":
        campaign = MemberEmailCampaign.objects.get(pk=item.object_id)
        if user is None:
            return None
        return render_broadcast(campaign, user=user)
    if item.kind == "ACTIVATION":
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.get(pk=item.object_id, is_active=True)
        if user.has_usable_password():
            return None
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        return render_transactional(item.kind, user=user,
            uid=uid, token=token,
            activation_url=f"{settings.SITE_ORIGIN}/reinitialiser/{uid}/{token}/")
    if item.kind == "APPLICATION":
        from apps.members.models import MembershipApplication
        application = MembershipApplication.objects.get(pk=item.object_id)
        return render_transactional(item.kind, first_name=application.first_name)
    if item.kind == "CONTACT":
        from .models import ContactRequest
        contact = ContactRequest.objects.get(pk=item.object_id)
        return render_transactional(item.kind, user=user, reference=str(contact.pk), contact_subject=contact.get_subject_display())
    notification = Notification.objects.select_related("recipient").get(pk=item.object_id)
    user = notification.recipient
    if item.kind == "EVENT_REMINDER":
        from apps.agenda.models import Event
        event = Event.objects.filter(pk=notification.target_id).first()
        # Un objet disparu ne doit jamais partir sous forme d'e-mail à moitié vide.
        if event is None:
            return None
        return render_transactional(item.kind, user=user, event=event)
    if item.kind == "DOCUMENT":
        from apps.documents.models import Document
        document = Document.objects.filter(pk=notification.target_id).first()
        if document is None:
            return None
        return render_transactional(item.kind, user=user, document=document)
    if item.kind == "VOTE_OPENED":
        from apps.voting.models import Vote
        vote = Vote.objects.filter(pk=notification.target_id).first()
        if vote is None:
            return None
        return render_transactional(item.kind, user=user, vote=vote)
    if item.kind == "VOTE_RESULTS":
        from apps.voting.models import Vote
        from apps.voting.selectors import can_view_results, vote_results
        vote = Vote.objects.filter(pk=notification.target_id).first()
        # L'e-mail ne donne jamais accès à un résultat devenu interdit entre la queue et l'envoi.
        if vote is None or not can_view_results(user, vote):
            return None
        return render_transactional(item.kind, user=user, vote=vote, results=vote_results(user, vote))
    if item.kind == "SATISFACTION_OPENED":
        from apps.satisfaction.models import SatisfactionPeriod
        period = SatisfactionPeriod.objects.filter(pk=notification.target_id).first()
        if period is None:
            return None
        return render_transactional(item.kind, user=user, period=period)
    return render_transactional(item.kind, user=user, notification=notification)

def deliver_batch(limit=20):
    if settings.EMAIL_BACKEND.endswith("dummy.EmailBackend"):
        return {"sent":0,"failed":0,"disabled":True}
    sent=failed=0
    for _ in range(min(max(limit,1),100)):
        with transaction.atomic():
            now=timezone.now()
            item=OutboxMessage.objects.select_for_update(skip_locked=True).filter(
                Q(state="PENDING",available_at__lte=now)|Q(state="SENDING",lease_until__lt=now)).order_by("available_at","created_at").first()
            if not item:break
            if item.attempts>=5:
                item.state="FAILED";item.error_code="attempt_limit";item.save();continue
            item.state="SENDING";item.attempts+=1;item.lease_token=uuid4();item.lease_until=now+timedelta(minutes=5);item.save()
            lease=item.lease_token
        # SMTP hors transaction ; identifiant stable, jamais de secret dans le journal.
        ok=False;not_applicable=False
        try:
            parts = _mail_parts(item)
            if parts is None:
                # Devenu définitivement non pertinent (mot de passe déjà défini, droit
                # retiré entre la mise en file et l'envoi, objet source disparu…) : un
                # nouvel essai ne changera jamais l'issue, donc pas de retry inutile.
                not_applicable=True
            else:
                subject, text_body, html_body = parts
                message=EmailMultiAlternatives(subject,text_body,settings.DEFAULT_FROM_EMAIL,[item.recipient],headers={"Message-ID":f"<{item.pk}@lionsmed-outbox.invalid>"})
                message.attach_alternative(html_body,"text/html")
                ok=message.send()==1
        except Exception:
            pass  # Code d'échec fixe ci-dessous, aucun message SMTP potentiellement nominatif.
        with transaction.atomic():
            current=OutboxMessage.objects.select_for_update().get(pk=item.pk)
            if current.lease_token!=lease:continue
            if ok:
                current.state="SENT";current.error_code=""
            elif not_applicable:
                current.state="FAILED";current.error_code="not_applicable"
            else:
                current.state="FAILED" if current.attempts>=5 else "PENDING"
                current.error_code="delivery_failed"
            current.sent_at=timezone.now() if ok else None
            current.available_at=timezone.now()+timedelta(minutes=2**current.attempts)
            current.lease_token=None;current.lease_until=None;current.save()
        sent+=int(ok);failed+=int(not ok)
        if item.kind == "MEMBER_BROADCAST":
            refresh_campaign_status(item.object_id)
    return {"sent":sent,"failed":failed,"disabled":False}
