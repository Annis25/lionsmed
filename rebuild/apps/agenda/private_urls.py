from django.urls import path
from . import private_views as v
app_name = "agenda_private"
urlpatterns = [
    path("calendrier/", v.calendar, name="calendar"),
    path("rendez-vous/<uuid:event_id>/inscription/", v.rsvp, name="rsvp"),
    path("presences/", v.attendance_events, name="attendance_events"),
    path("presences/<uuid:event_id>/", v.attendance_sheet, name="attendance_sheet"),
]
