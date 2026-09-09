from django.urls import path
from . import public_views as v
app_name = "members_public"
urlpatterns = [
    path("membres/<slug:slug>/", v.detail, name="detail"),
    path("membres/<slug:slug>/photo/", v.photo, name="photo"),
]
