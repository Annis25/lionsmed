from django.urls import path
from . import views
from . import admin_views

urlpatterns = [
    # Auth
    path('connexion/', views.login_view, name='login'),
    path('deconnexion/', views.logout_view, name='logout'),
    # Espace membre
    path('espace-membre/', views.dashboard, name='dashboard'),
    path('espace-membre/profil/', views.profile_view, name='profile'),
    path('espace-membre/calendrier/', views.calendar_view, name='calendar'),
    path('espace-membre/votes/', views.votes_view, name='votes'),
    path('espace-membre/notifications/', views.notifications_view, name='notifications_list'),
    path('espace-membre/documents/', views.documents_view, name='documents'),
    path('espace-membre/documents/<int:doc_id>/telecharger/', views.document_download, name='document_download'),
    # Panel admin custom
    path('admin-panel/', admin_views.admin_dashboard, name='admin_dashboard'),
    path('admin-panel/membres/', admin_views.admin_members, name='admin_members'),
    path('admin-panel/membres/<int:user_id>/edit/', admin_views.admin_member_edit, name='admin_member_edit'),
    path('admin-panel/candidatures/', admin_views.admin_requests, name='admin_requests'),
    path('admin-panel/candidatures/<int:req_id>/action/', admin_views.admin_request_action, name='admin_request_action'),
    path('admin-panel/cotisations/', admin_views.admin_cotisations, name='admin_cotisations'),
    path('admin-panel/notifications/envoyer/', admin_views.admin_send_notification, name='admin_send_notification'),
    # Panel admin — contenu éditorial
    path('admin-panel/evenements/', admin_views.admin_events_list, name='admin_events'),
    path('admin-panel/evenements/nouveau/', admin_views.admin_event_create, name='admin_event_create'),
    path('admin-panel/evenements/<int:event_id>/edit/', admin_views.admin_event_edit, name='admin_event_edit'),
    path('admin-panel/evenements/<int:event_id>/supprimer/', admin_views.admin_event_delete, name='admin_event_delete'),
    path('admin-panel/actualites/', admin_views.admin_articles_list, name='admin_articles'),
    path('admin-panel/actualites/nouveau/', admin_views.admin_article_create, name='admin_article_create'),
    path('admin-panel/actualites/<int:article_id>/edit/', admin_views.admin_article_edit, name='admin_article_edit'),
    path('admin-panel/actualites/<int:article_id>/statut/', admin_views.admin_article_toggle_status, name='admin_article_toggle_status'),
    path('admin-panel/actualites/<int:article_id>/supprimer/', admin_views.admin_article_delete, name='admin_article_delete'),
]
