from django import forms
from apps.accounts.forms import StyledFields
from .models import EditorialSection,ClubIdentity,ImpactMetric
class ImageForm(StyledFields,forms.Form):
    photo=forms.FileField(label="Photo",widget=forms.FileInput(attrs={"accept":"image/jpeg,image/png,image/webp"}))
    alt=forms.CharField(label="Description factuelle",max_length=250)
    source=forms.CharField(label="Source et droits vérifiés",max_length=300)
    approved=forms.BooleanField(label="Je confirme l’autorisation de publication de cette image.")
class SectionForm(StyledFields,forms.ModelForm):
    validated=forms.BooleanField(label="Texte et source validés pour publication",required=False)
    class Meta:
        model=EditorialSection;fields=["key","title","body","source"]
        labels={"key":"Rubrique","title":"Titre","body":"Texte","source":"Source de validation"}
class IdentityForm(StyledFields,forms.ModelForm):
    validated=forms.BooleanField(label="Coordonnées validées pour publication",required=False)
    class Meta:
        model=ClubIdentity;fields=["contact_email","phone","postal_address","source"]
        labels={"contact_email":"Email public confirmé","phone":"Téléphone public confirmé","postal_address":"Adresse publique confirmée","source":"Source"}
class MetricForm(StyledFields,forms.ModelForm):
    validated=forms.BooleanField(label="Valeur, source et période validées",required=False)
    class Meta:
        model=ImpactMetric;fields=["label","value","starts_on","ends_on","source"]
        labels={"label":"Libellé humain","value":"Valeur","starts_on":"Début de période","ends_on":"Fin de période","source":"Source"}
        widgets={"starts_on":forms.DateInput(format="%Y-%m-%d",attrs={"type":"date"}),"ends_on":forms.DateInput(format="%Y-%m-%d",attrs={"type":"date"})}
