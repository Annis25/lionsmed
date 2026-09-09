from django.urls import path
from . import views
app_name = "satisfaction"
urlpatterns = [
    path("satisfaction/", views.respond, name="respond"),
    path("satisfaction/gestion/", views.manage_list, name="manage_list"),
    path("satisfaction/gestion/<uuid:period_id>/resultats/", views.results, name="results"),
]
