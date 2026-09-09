from django.contrib import admin
from django.urls import include, path
from apps.core import views
from apps.editorial import views as public_views

urlpatterns = [
    path("espace/", include("apps.editorial.management_urls")),
    path("", include("apps.editorial.urls")),
    path("", include("apps.service_actions.urls")),
    path("", include("apps.agenda.urls")),
    path("", include("apps.communications.urls")),
    path("", include("apps.members.public_urls")),
    path("espace/", include("apps.members.urls")),
    path("espace/", include("apps.governance.urls")),
    path("espace/", include("apps.agenda.private_urls")),
    path("espace/", include("apps.documents.urls")),
    path("espace/", include("apps.dues.urls")),
    path("espace/", include("apps.communications.private_urls")),
    path("espace/", include("apps.voting.urls")),
    path("espace/", include("apps.satisfaction.urls")),
    path("", include(([path("", public_views.home, name="home"),
                       path("espace/", views.dashboard, name="dashboard"),
                       path("robots.txt", public_views.robots, name="robots")], "core"))),
    path("", include("apps.accounts.urls")),
    path("admin/", admin.site.urls),
]
