from django.urls import path
from apps.editorial import views
app_name="agenda"
urlpatterns=[path("evenements/",views.listing,{"kind":"event"},name="list"),path("evenements/<slug:slug>/",views.detail,{"kind":"event"},name="detail")]
