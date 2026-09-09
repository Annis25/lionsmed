from django.urls import path
from . import private_views as v
app_name = "notifications"
urlpatterns = [
    path("notifications/", v.notification_list, name="list"),
    path("notifications/tout-lire/", v.notification_mark_all_read, name="mark_all_read"),
    path("notifications/<uuid:notification_id>/lue/", v.notification_mark_read, name="mark_read"),
    path("notifications/gestion/envoyer/", v.notification_send, name="send"),
]
