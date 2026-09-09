from django.urls import path
from . import views
app_name="members"
urlpatterns=[
    path("profil/",views.profile,name="profile"),
    path("profil/modifier/",views.edit_profile,name="profile_edit"),
    path("profil/email/",views.email_information,name="email_information"),
    path("annuaire/",views.directory,name="directory"),
    path("membres/<uuid:user_id>/",views.detail,name="detail"),
    path("membres/<uuid:user_id>/photo/",views.photo,name="photo"),
    path("parcours/",views.experiences,name="experiences"),
    path("parcours/ajouter/",views.experience_edit,name="experience_add"),
    path("parcours/<uuid:experience_id>/modifier/",views.experience_edit,name="experience_edit"),
    path("parcours/<uuid:experience_id>/supprimer/",views.experience_delete,name="experience_delete"),
]
