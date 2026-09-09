from django.db import models
from django.urls import reverse
from apps.editorial.models import Publication

class Axis(models.TextChoices):
    DIABETE="DIABETE","Diabète"
    ENVIRONNEMENT="ENVIRONNEMENT","Environnement"
    HUMANITAIRE="HUMANITAIRE","Humanitaire"
    JEUNESSE="JEUNESSE","Jeunesse"

class Action(Publication):
    axis=models.CharField(max_length=20,choices=Axis.choices)
    performed_on=models.DateField(null=True,blank=True)
    location=models.CharField(max_length=200,blank=True)
    city=models.CharField(max_length=100,blank=True)
    country=models.CharField(max_length=100,blank=True)
    beneficiaries=models.PositiveIntegerField(null=True,blank=True)
    partners=models.TextField(max_length=1000,blank=True)
    evidence=models.CharField(max_length=300,blank=True,help_text="Source du bilan, bénéficiaires ou partenaires")
    def get_absolute_url(self):return reverse("actions:detail",args=[self.slug])
    class Meta(Publication.Meta):
        constraints=Publication.Meta.constraints+[models.CheckConstraint(condition=models.Q(axis__in=Axis.values),name="action_axis_valid")]

class ActionPhoto(models.Model):
    action=models.ForeignKey(Action,on_delete=models.PROTECT,related_name="photos")
    image=models.ForeignKey("core.PublicImage",on_delete=models.PROTECT)
    position=models.PositiveSmallIntegerField(default=0)
    caption=models.CharField(max_length=300,blank=True)
    class Meta:
        ordering=["position","id"]
        constraints=[models.UniqueConstraint(fields=["action","position"],name="action_photo_position"),models.UniqueConstraint(fields=["action","image"],name="action_photo_image")]
