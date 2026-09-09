from django.urls import path
from . import views
app_name = "voting"
urlpatterns = [
    path("votes/", views.member_list, name="member_list"),
    path("votes/nouveau/", views.manage_create, name="manage_create"),
    path("votes/gestion/", views.manage_list, name="manage_list"),
    path("votes/<uuid:vote_id>/", views.member_detail, name="member_detail"),
    path("votes/<uuid:vote_id>/envoyer/", views.member_confirm, name="member_confirm"),
    path("votes/<uuid:vote_id>/resultats/", views.results, name="results"),
    path("votes/<uuid:vote_id>/gestion/", views.manage_detail, name="manage_detail"),
    path("votes/<uuid:vote_id>/gestion/options/<uuid:option_id>/retirer/", views.manage_option_remove, name="manage_option_remove"),
    path("votes/<uuid:vote_id>/ouvrir/", views.manage_open, name="manage_open"),
    path("votes/<uuid:vote_id>/suivi/", views.manage_track, name="manage_track"),
    path("votes/<uuid:vote_id>/cloturer/", views.manage_close, name="manage_close"),
]
