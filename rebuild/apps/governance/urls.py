from django.urls import path
from . import views
app_name="governance"
urlpatterns=[path("pilotage/",views.dashboard,name="dashboard"),path("gestion/membres/",views.members,name="members"),
    path("gestion/membres/<uuid:user_id>/",views.member,name="member"),path("gestion/annees/",views.years,name="years"),
    path("statistiques/",views.statistics,name="statistics")]
