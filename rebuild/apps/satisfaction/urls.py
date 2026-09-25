from django.urls import path
from . import views
app_name = "satisfaction"
urlpatterns = [
    path("satisfaction/", views.respond, name="respond"),
    path("satisfaction/gestion/", views.manage_list, name="manage_list"),
    path("satisfaction/gestion/<uuid:period_id>/modifier/", views.edit, name="edit"),
    path("satisfaction/gestion/<uuid:period_id>/resultats/", views.results, name="results"),
    path("satisfaction/gestion/<uuid:period_id>/reponses/", views.individual, name="individual"),
    path("satisfaction/gestion/<uuid:period_id>/axes/ajouter/", views.axis_add, name="axis_add"),
    path("satisfaction/gestion/<uuid:period_id>/axes/<int:axis_id>/modifier/", views.axis_edit, name="axis_edit"),
    path("satisfaction/gestion/<uuid:period_id>/axes/<int:axis_id>/supprimer/", views.axis_delete, name="axis_delete"),
    path("satisfaction/gestion/<uuid:period_id>/axes/<int:axis_id>/deplacer/", views.axis_move, name="axis_move"),
]
