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
    # Panel admin custom
    path('admin-panel/', admin_views.admin_dashboard, name='admin_dashboard'),
    path('admin-panel/membres/', admin_views.admin_members, name='admin_members'),
    path('admin-panel/membres/<int:user_id>/edit/', admin_views.admin_member_edit, name='admin_member_edit'),
    path('admin-panel/candidatures/', admin_views.admin_requests, name='admin_requests'),
    path('admin-panel/candidatures/<int:req_id>/action/', admin_views.admin_request_action, name='admin_request_action'),
    path('admin-panel/cotisations/', admin_views.admin_cotisations, name='admin_cotisations'),
    path('admin-panel/notifications/envoyer/', admin_views.admin_send_notification, name='admin_send_notification'),
]
