from django.urls import path
from . import views
app_name="governance"
urlpatterns=[path("gestion/membres/",views.members,name="members"),
    path("gestion/membres/ajouter/",views.member_add,name="member_add"),
    path("gestion/membres/<uuid:user_id>/",views.member,name="member"),
    path("gestion/membres/<uuid:user_id>/role/",views.member_set_role,name="member_set_role"),
    path("gestion/membres/<uuid:user_id>/statut/",views.member_set_status,name="member_set_status"),
    path("gestion/membres/<uuid:user_id>/email/",views.member_set_email,name="member_set_email"),
    path("gestion/membres/<uuid:user_id>/renvoyer-invitation/",views.member_resend_invitation,name="member_resend_invitation"),
    path("gestion/mandats/",views.mandates,name="mandates"),
    path("gestion/mandats/ajouter/",views.mandate_edit,name="mandate_add"),
    path("gestion/mandats/<uuid:mandate_id>/modifier/",views.mandate_edit,name="mandate_edit"),
    path("gestion/mandats/<uuid:mandate_id>/terminer/",views.mandate_end,name="mandate_end"),
    path("gestion/mandats/<uuid:mandate_id>/supprimer/",views.mandate_delete,name="mandate_delete"),
    path("gestion/annees/",views.years,name="years"),
    path("gestion/annees/<int:year_id>/activer/",views.year_activate,name="year_activate"),
    path("gestion/annees/<int:year_id>/archiver/",views.year_archive_toggle,name="year_archive_toggle"),
    path("statistiques/",views.statistics,name="statistics")]
