from datetime import timedelta
from uuid import uuid4
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from .models import OutboxMessage

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
        ok=False
        try:
            context={"origin":settings.SITE_ORIGIN,"reference":str(item.object_id)}
            stem={"APPLICATION":"application_receipt","CONTACT":"contact_notice","EVENT_REMINDER":"event_reminder",
                "IMPORTANT":"notification_important","DOCUMENT":"notification_document",
                "VOTE_OPENED":"ouverture_vote","VOTE_RESULTS":"resultats_vote","SATISFACTION_OPENED":"satisfaction"}[item.kind]
            subject={"APPLICATION":"Candidature reçue — Lions Club Sfax-Méditerranée",
                "CONTACT":"Nouveau message de contact — Lions Club Sfax-Méditerranée",
                "EVENT_REMINDER":"Rappel de rendez-vous — Lions Club Sfax-Méditerranée",
                "IMPORTANT":"Notification importante — Lions Club Sfax-Méditerranée",
                "DOCUMENT":"Nouveau document — Lions Club Sfax-Méditerranée",
                "VOTE_OPENED":"Ouverture d'un vote — Lions Club Sfax-Méditerranée",
                "VOTE_RESULTS":"Résultats d'un vote — Lions Club Sfax-Méditerranée",
                "SATISFACTION_OPENED":"Satisfaction du mois — Lions Club Sfax-Méditerranée"}[item.kind]
            message=EmailMultiAlternatives(subject,render_to_string("emails/"+stem+".txt",context),settings.DEFAULT_FROM_EMAIL,[item.recipient],headers={"Message-ID":f"<{item.pk}@lionsmed-outbox.invalid>"})
            message.attach_alternative(render_to_string("emails/"+stem+".html",context),"text/html")
            ok=message.send()==1
        except Exception:
            pass  # Code d'échec fixe ci-dessous, aucun message SMTP potentiellement nominatif.
        with transaction.atomic():
            current=OutboxMessage.objects.select_for_update().get(pk=item.pk)
            if current.lease_token!=lease:continue
            current.state="SENT" if ok else "FAILED" if current.attempts>=5 else "PENDING"
            current.sent_at=timezone.now() if ok else None
            current.error_code="" if ok else "delivery_failed"
            current.available_at=timezone.now()+timedelta(minutes=2**current.attempts)
            current.lease_token=None;current.lease_until=None;current.save()
        sent+=int(ok);failed+=int(not ok)
    return {"sent":sent,"failed":failed,"disabled":False}
