from django.db import models
from django.urls import reverse
from apps.editorial.models import Publication, PublicationQuerySet
class EventQuerySet(PublicationQuerySet):
    def public(self):return super().public().filter(visibility="PUBLIC")
class Event(Publication):
    starts_at=models.DateTimeField(null=True,blank=True)
    ends_at=models.DateTimeField(null=True,blank=True)
    location=models.CharField(max_length=200,blank=True)
    category=models.CharField(max_length=20,choices=[("RENCONTRE","Rencontre"),("REUNION","Réunion"),("FORMATION","Formation"),("AUTRE","Autre")],default="RENCONTRE")
    visibility=models.CharField(max_length=8,choices=[("PUBLIC","Public"),("PRIVATE","Privé")],default="PRIVATE")
    objects=EventQuerySet.as_manager()
    def get_absolute_url(self):return reverse("agenda:detail",args=[self.slug])
    class Meta(Publication.Meta):
        constraints=Publication.Meta.constraints+[models.CheckConstraint(condition=models.Q(ends_at__isnull=True)|models.Q(starts_at__isnull=False,ends_at__gt=models.F("starts_at")),name="event_dates_valid")]
