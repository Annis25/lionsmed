import uuid
from django.conf import settings
from django.db import models
from django.urls import reverse
from apps.editorial.models import Publication, PublicationQuerySet
class EventQuerySet(PublicationQuerySet):
    def public(self):return super().public().filter(visibility="PUBLIC")
class Event(Publication):
    starts_at=models.DateTimeField(null=True,blank=True)
    ends_at=models.DateTimeField(null=True,blank=True)
    all_day=models.BooleanField(default=False,help_text="Événement journée entière — heures ignorées à l'affichage.")
    location=models.CharField(max_length=200,blank=True)
    meeting_link=models.URLField(max_length=300,blank=True,help_text="Lien de réunion (visioconférence), facultatif.")
    category=models.CharField(max_length=20,choices=[("RENCONTRE","Rencontre"),("REUNION","Réunion"),("FORMATION","Formation"),("AUTRE","Autre")],default="RENCONTRE")
    visibility=models.CharField(max_length=8,choices=[("PUBLIC","Public"),("PRIVATE","Privé")],default="PRIVATE")
    capacity=models.PositiveIntegerField(null=True,blank=True,help_text="Places disponibles pour l'inscription, si limitée")
    registration_enabled=models.BooleanField(default=False)
    objects=EventQuerySet.as_manager()
    def get_absolute_url(self):return reverse("agenda:detail",args=[self.slug])
    class Meta(Publication.Meta):
        constraints=Publication.Meta.constraints+[
            models.CheckConstraint(condition=models.Q(ends_at__isnull=True)|models.Q(starts_at__isnull=False,ends_at__gt=models.F("starts_at")),name="event_dates_valid"),
            models.CheckConstraint(condition=models.Q(capacity__isnull=True)|models.Q(capacity__gt=0),name="event_capacity_positive"),
        ]

class Registration(models.Model):
    class Status(models.TextChoices):
        PENDING="PENDING","En attente"
        CONFIRMED="CONFIRMED","Confirmée"
        CANCELLED="CANCELLED","Annulée"
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    event=models.ForeignKey(Event,on_delete=models.PROTECT,related_name="registrations")
    profile=models.ForeignKey("members.MemberProfile",on_delete=models.PROTECT,related_name="registrations")
    status=models.CharField(max_length=10,choices=Status.choices,default=Status.PENDING)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        ordering=["-created_at"]
        constraints=[
            models.UniqueConstraint(fields=["event","profile"],name="registration_unique_event_profile"),
            models.CheckConstraint(condition=models.Q(status__in=["PENDING","CONFIRMED","CANCELLED"]),name="registration_status_valid"),
        ]

class Attendance(models.Model):
    class Status(models.TextChoices):
        PRESENT="PRESENT","Présent"
        ABSENT="ABSENT","Absent"
        EXCUSED="EXCUSED","Excusé"
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    event=models.ForeignKey(Event,on_delete=models.PROTECT,related_name="attendances")
    profile=models.ForeignKey("members.MemberProfile",on_delete=models.PROTECT,related_name="attendances")
    status=models.CharField(max_length=10,choices=Status.choices)
    note=models.CharField(max_length=300,blank=True)
    recorded_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="attendances_recorded")
    recorded_at=models.DateTimeField(auto_now=True)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=["-recorded_at"]
        constraints=[
            models.UniqueConstraint(fields=["event","profile"],name="attendance_unique_event_profile"),
            models.CheckConstraint(condition=models.Q(status__in=["PRESENT","ABSENT","EXCUSED"]),name="attendance_status_valid"),
        ]
