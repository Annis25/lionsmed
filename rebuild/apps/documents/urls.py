from django.urls import path
from . import views
app_name = "documents"
urlpatterns = [
    path("documents/", views.document_list, name="list"),
    path("documents/deposer/", views.document_upload, name="upload"),
    path("documents/gestion/", views.manage_list, name="manage_list"),
    path("documents/gestion/<uuid:document_id>/", views.manage_detail, name="manage_detail"),
    path("documents/gestion/<uuid:document_id>/revoquer/<uuid:grant_id>/", views.manage_revoke, name="manage_revoke"),
    path("documents/<uuid:document_id>/", views.document_detail, name="detail"),
    path("documents/<uuid:document_id>/telecharger/", views.document_download, name="download"),
]
