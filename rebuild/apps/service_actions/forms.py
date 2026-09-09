from django import forms
from django.core.exceptions import PermissionDenied
from urllib.parse import urlsplit
from apps.accounts.forms import StyledFields
from apps.core.permissions import can
from apps.core.models import PublicImage
from .models import Action


class MultipleImageInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    widget = MultipleImageInput

    def clean(self, data, initial=None):
        if not data:
            return []
        return [super(MultipleImageField, self).clean(item, initial) for item in data]


class ActionForm(StyledFields, forms.ModelForm):
    main_image_upload = forms.ImageField(label="Image principale (image 1)", required=False)
    gallery_uploads = MultipleImageField(label="Autres images (9 maximum)", required=False)
    class Meta:
        model=Action
        fields=["title","summary","body"]+["axis","performed_on","location","city","country","beneficiaries","hours_worked","partners","instagram_url"]
        labels={"title":"Titre","summary":"Résumé","body":"Récit / description","performed_on":"Date de réalisation","location":"Lieu","city":"Ville","country":"Pays","axis":"Axe","beneficiaries":"Bénéficiaires (si validés)","hours_worked":"Heures de travail","partners":"Partenaires validés","instagram_url":"Lien de la publication Instagram"}
        widgets={"performed_on":forms.DateInput(attrs={"type":"date"},format="%Y-%m-%d"),"starts_at":forms.DateTimeInput(attrs={"type":"datetime-local"},format="%Y-%m-%dT%H:%M"),"ends_at":forms.DateTimeInput(attrs={"type":"datetime-local"},format="%Y-%m-%dT%H:%M"),"body":forms.Textarea(attrs={"rows":6}),"summary":forms.Textarea(attrs={"rows":3})}
    def __init__(self,*args,actor,**kwargs):
        instance=kwargs.get("instance")
        if not can(actor,"action.edit" if instance else "action.create",instance):raise PermissionDenied
        super().__init__(*args,**kwargs)
        self.fields["gallery_uploads"].widget.attrs["multiple"] = True

    def clean_instagram_url(self):
        value=self.cleaned_data["instagram_url"]
        if not value:
            return value
        hostname=(urlsplit(value).hostname or "").lower()
        if hostname not in {"instagram.com","www.instagram.com","m.instagram.com","instagr.am"}:
            raise forms.ValidationError("Utilisez un lien Instagram valide.")
        return value

    def clean(self):
        cleaned = super().clean()
        uploads = [cleaned.get("main_image_upload")] + cleaned.get("gallery_uploads", [])
        uploads = [upload for upload in uploads if upload]
        if len(cleaned.get("gallery_uploads", [])) + self.instance.photos.count() > 9:
            self.add_error("gallery_uploads", "Une action peut avoir au plus neuf images supplémentaires, en plus de l’image principale.")
        return cleaned
