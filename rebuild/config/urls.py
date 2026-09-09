from django.contrib import admin
from django.urls import include, path
from apps.core import views

urlpatterns = [
    path("espace/", include("apps.members.urls")),
    path("espace/", include("apps.governance.urls")),
    path("", include(([path("", views.home, name="home"),
                       path("espace/", views.dashboard, name="dashboard"),
                       path("robots.txt", views.robots, name="robots")], "core"))),
    path("", include("apps.accounts.urls")),
    path("admin/", admin.site.urls),
]
