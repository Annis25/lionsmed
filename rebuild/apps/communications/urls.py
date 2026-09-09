from django.urls import path
from . import views as v
app_name="communications"
urlpatterns=[path("candidature/",v.public_form,{"kind":"application"},name="application"),path("contact/",v.public_form,{"kind":"contact"},name="contact"),path("candidature/recue/",v.done,{"kind":"application"},name="application_done"),path("contact/recu/",v.done,{"kind":"contact"},name="contact_done"),path("espace/demandes/<str:kind>/",v.inbox,name="inbox"),path("espace/demandes/<str:kind>/<uuid:object_id>/",v.inbox,name="request")]
