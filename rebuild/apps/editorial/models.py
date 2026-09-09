import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.urls import reverse

class PublicationQuerySet(models.QuerySet):
    def public(self):
        return self.filter(status="PUBLISHED", published_at__lte=timezone.now())

class Publication(models.Model):
    class Status(models.TextChoices):
        DRAFT="DRAFT","Brouillon"
        REVIEW="REVIEW","À valider"
        PUBLISHED="PUBLISHED","Publié"
        ARCHIVED="ARCHIVED","Retiré"
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    title=models.CharField(max_length=180)
    slug=models.SlugField(max_length=200,unique=True)
    summary=models.TextField(max_length=500,blank=True)
    body=models.TextField(max_length=20000,blank=True)
    status=models.CharField(max_length=12,choices=Status.choices,default=Status.DRAFT)
    published_at=models.DateTimeField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="%(app_label)s_%(class)s_created")
    updated_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="%(app_label)s_%(class)s_updated")
    meta_title=models.CharField(max_length=180,blank=True)
    meta_description=models.CharField(max_length=300,blank=True)
    cover=models.ForeignKey("core.PublicImage",on_delete=models.PROTECT,null=True,blank=True,related_name="%(app_label)s_%(class)s_covers")
    social_image=models.ForeignKey("core.PublicImage",on_delete=models.PROTECT,null=True,blank=True,related_name="%(app_label)s_%(class)s_socials")
    objects=PublicationQuerySet.as_manager()
    class Meta:
        abstract=True
        ordering=["-published_at","id"]
        constraints=[models.CheckConstraint(condition=models.Q(status__in=["DRAFT","REVIEW","PUBLISHED","ARCHIVED"]),name="%(app_label)s_%(class)s_status"),models.CheckConstraint(condition=~models.Q(status="PUBLISHED")|models.Q(published_at__isnull=False),name="%(app_label)s_%(class)s_pub_date")]

class NewsArticle(Publication):
    category=models.CharField(max_length=20,choices=[("VIE","Vie du club"),("PASSATION","Passation"),("PARTENARIAT","Partenariat"),("DISTINCTION","Distinction"),("COMMUNIQUE","Communiqué")],default="VIE")
    author_name=models.CharField(max_length=150,blank=True,help_text="Signature publique validée seulement")
    def get_absolute_url(self):return reverse("editorial:news_detail",args=[self.slug])

class EditorialSection(models.Model):
    KEYS=[("club_intro","Présentation du club"),("club_history","Histoire documentée"),("club_values","Valeurs"),("club_movement","Mouvement Lions"),("join_service","Rejoindre : servir"),("join_belonging","Rejoindre : appartenir"),("join_growth","Rejoindre : progresser"),("legal","Mentions légales"),("privacy","Confidentialité"),("axis_diabete","Axe Diabète"),("axis_environnement","Axe Environnement"),("axis_humanitaire","Axe Humanitaire"),("axis_jeunesse","Axe Jeunesse")]
    key=models.CharField(primary_key=True,max_length=32,choices=KEYS)
    title=models.CharField(max_length=180)
    body=models.TextField(max_length=20000)
    source=models.CharField(max_length=300)
    validated_at=models.DateTimeField(null=True,blank=True)
    updated_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        constraints=[models.CheckConstraint(condition=models.Q(key__in=["club_intro","club_history","club_values","club_movement","join_service","join_belonging","join_growth","legal","privacy","axis_diabete","axis_environnement","axis_humanitaire","axis_jeunesse"]),name="editorial_known_key")]

class ClubIdentity(models.Model):
    id=models.PositiveSmallIntegerField(primary_key=True,default=1,editable=False)
    contact_email=models.EmailField(blank=True)
    phone=models.CharField(max_length=32,blank=True)
    postal_address=models.CharField(max_length=300,blank=True)
    source=models.CharField(max_length=300)
    validated_at=models.DateTimeField(null=True,blank=True)
    updated_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        constraints=[models.CheckConstraint(condition=models.Q(id=1),name="identity_singleton")]

class ImpactMetric(models.Model):
    label=models.CharField(max_length=100)
    value=models.PositiveIntegerField()
    starts_on=models.DateField()
    ends_on=models.DateField()
    source=models.CharField(max_length=300)
    validated_at=models.DateTimeField(null=True,blank=True)
    updated_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        constraints=[models.CheckConstraint(condition=models.Q(ends_on__gte=models.F("starts_on")),name="metric_dates")]

class Redirect(models.Model):
    old_path=models.CharField(max_length=300,unique=True)
    new_path=models.CharField(max_length=300)
    created_at=models.DateTimeField(auto_now_add=True)
    def clean(self):
        from django.core.exceptions import ValidationError
        from urllib.parse import urlsplit
        for path in (self.old_path,self.new_path):
            if not path.startswith("/") or path.startswith("//") or "\\" in path or "%" in path or any(ord(c)<32 for c in path) or urlsplit(path).netloc or urlsplit(path).query or urlsplit(path).fragment:
                raise ValidationError("Chemin interne simple requis.")
        if self.old_path==self.new_path:raise ValidationError("Boucle de redirection interdite.")
        if type(self).objects.exclude(pk=self.pk).filter(old_path=self.new_path).exists():
            raise ValidationError("La destination doit être une URL finale, sans redirection.")
