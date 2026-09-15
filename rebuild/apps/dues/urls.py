from django.urls import path
from . import views
app_name = "dues"
urlpatterns = [
    path("cotisations/gestion/annee/<int:year_id>/membre/<int:profile_id>/tranche/<int:tranche>/", views.manage_set, name="manage_set"),
    path("cotisations/", views.own, name="own"),
    path("cotisations/gestion/", views.manage_list, name="manage_list"),
    path("cotisations/gestion/montants/", views.manage_schedule, name="manage_schedule"),
    path("cotisations/gestion/<uuid:record_id>/", views.manage_detail, name="manage_detail"),
    path("cotisations/gestion/<uuid:record_id>/tranche/<int:tranche>/", views.manage_toggle_tranche, name="manage_toggle_tranche"),
]
