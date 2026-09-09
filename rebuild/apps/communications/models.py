import uuid
from django.db import models
from django.utils import timezone
class ContactRequest(models.Model):
    SUBJECTS=[("GENERAL","Question générale"),("PARTENARIAT","Proposition de partenariat"),("ACTION","Action ou initiative"),("PRESSE","Presse / communication"),("ADHESION","Question sur l’adhésion"),("AUTRE","Autre demande")]
    STATES=[("RECEIVED","Reçu"),("CONTACTED","Contact établi"),("FOLLOW_UP","En suivi"),("CLOSED","Clos")]
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    submission_key=models.UUIDField(unique=True)
    name=models.CharField(max_length=150)
    email=models.EmailField()
    subject=models.CharField(max_length=20,choices=SUBJECTS)
    message=models.TextField(max_length=5000)
    state=models.CharField(max_length=12,choices=STATES,default="RECEIVED")
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    notice_version=models.CharField(max_length=32,default="lot3-v1")
    class Meta:
        ordering=["-created_at","id"]
        constraints=[models.CheckConstraint(condition=models.Q(state__in=["RECEIVED","CONTACTED","FOLLOW_UP","CLOSED"]),name="contact_state_valid")]

class OutboxMessage(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    event_key=models.CharField(max_length=150,unique=True)
    kind=models.CharField(max_length=20,choices=[("APPLICATION","Accusé candidature"),("CONTACT","Avis contact interne")])
    recipient=models.EmailField()
    object_id=models.UUIDField()
    attempts=models.PositiveSmallIntegerField(default=0)
    state=models.CharField(max_length=8,choices=[("PENDING","En attente"),("SENDING","En cours"),("SENT","Envoyé"),("FAILED","Échec")],default="PENDING")
    available_at=models.DateTimeField(default=timezone.now)
    lease_until=models.DateTimeField(null=True,blank=True)
    lease_token=models.UUIDField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    sent_at=models.DateTimeField(null=True,blank=True)
    error_code=models.CharField(max_length=32,blank=True)
    class Meta:
        indexes=[models.Index(fields=["state","available_at"],name="outbox_ready_idx")]
