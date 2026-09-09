from django.urls import path
from . import views
app_name="governance"
urlpatterns=[path("gestion/membres/",views.members,name="members"),
    path("gestion/membres/ajouter/",views.member_add,name="member_add"),
    path("gestion/membres/<uuid:user_id>/",views.member,name="member"),
    path("gestion/membres/<uuid:user_id>/role/",views.member_set_role,name="member_set_role"),
    path("gestion/membres/<uuid:user_id>/statut/",views.member_set_status,name="member_set_status"),
    path("gestion/membres/<uuid:user_id>/email/",views.member_set_email,name="member_set_email"),
    path("gestion/annees/",views.years,name="years"),
    path("gestion/annees/<int:year_id>/activer/",views.year_activate,name="year_activate"),
    path("gestion/annees/<int:year_id>/archiver/",views.year_archive_toggle,name="year_archive_toggle"),
    path("statistiques/",views.statistics,name="statistics")]
