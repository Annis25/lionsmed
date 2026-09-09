from django.urls import path
from . import private_views as v
app_name = "agenda_private"
urlpatterns = [
    path("calendrier/", v.calendar, name="calendar"),
    path("calendrier/evenements/ajouter/", v.calendar_event_add, name="calendar_event_add"),
    path("calendrier/telecharger.ics", v.calendar_download, name="calendar_download"),
    path("calendrier/lien/regenerer/", v.calendar_token_regenerate, name="calendar_token_regenerate"),
    path("calendrier/abonnement/<str:token>.ics", v.calendar_subscribe, name="calendar_subscribe"),
    path("rendez-vous/<uuid:event_id>/inscription/", v.rsvp, name="rsvp"),
    path("presences/", v.attendance_events, name="attendance_events"),
    path("presences/<uuid:event_id>/", v.attendance_sheet, name="attendance_sheet"),
]
