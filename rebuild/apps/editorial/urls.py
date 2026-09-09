from django.urls import path
from django.contrib.sitemaps.views import sitemap
from . import views
from .sitemaps import PublicSitemap
app_name="editorial"
urlpatterns=[path("notre-club/",views.page,{"page":"club"},name="club"),path("rejoindre/",views.page,{"page":"join"},name="join"),path("mentions-legales/",views.page,{"page":"legal"},name="legal"),path("confidentialite/",views.page,{"page":"privacy"},name="privacy"),path("plan-du-site/",views.page,{"page":"sitemap"},name="sitemap"),path("actualites/",views.listing,{"kind":"news"},name="news"),path("actualites/<slug:slug>/",views.detail,{"kind":"news"},name="news_detail"),path("images-publiques/<uuid:image_id>/<int:size>/",views.image,name="image"),path("sitemap.xml",sitemap,{"sitemaps":{"public":PublicSitemap}},name="sitemap_xml")]
