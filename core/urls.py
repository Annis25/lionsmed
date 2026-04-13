from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('a-propos/', views.about, name='about'),
    path('nos-actions/', views.actions, name='actions'),
    path('evenements/', views.evenements_list, name='evenements'),
    path('evenements/<slug:slug>/', views.evenement_detail, name='evenement_detail'),
    path('actualites/', views.actualites_list, name='actualites'),
    path('actualites/<slug:slug>/', views.actualite_detail, name='actualite_detail'),
    path('rejoindre/', views.rejoindre, name='rejoindre'),
    path('contact/', views.contact, name='contact'),
]
