from django.urls import path
from apps.editorial import views
app_name="actions"
urlpatterns=[path("nos-actions/",views.listing,{"kind":"action"},name="list"),path("nos-actions/<slug:slug>/",views.detail,{"kind":"action"},name="detail")]
