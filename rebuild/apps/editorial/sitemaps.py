from django.contrib.sitemaps import Sitemap
from django.conf import settings
from django.urls import reverse
from apps.service_actions.models import Action
from apps.agenda.models import Event
from .models import EditorialSection

class PublicSitemap(Sitemap):
    def items(self):
        if not settings.PUBLIC_INDEXING_ENABLED:return []
        paths=["core:home","editorial:club","actions:list","editorial:join","communications:contact","editorial:sitemap"]
        if Event.objects.public().exists():paths.append("agenda:list")
        for key in ["legal","privacy"]:
            if EditorialSection.objects.filter(key=key,validated_at__isnull=False).exists():paths.append("editorial:"+key)
        return paths+list(Action.objects.public())+list(Event.objects.public())
    def location(self,item):return reverse(item) if isinstance(item,str) else item.get_absolute_url()
    def lastmod(self,item):return None if isinstance(item,str) else item.updated_at
    def get_urls(self,page=1,site=None,protocol=None):
        from urllib.parse import urlsplit
        from types import SimpleNamespace
        origin=urlsplit(settings.SITE_ORIGIN)
        return super().get_urls(page,SimpleNamespace(domain=origin.netloc,name=origin.netloc),origin.scheme)
