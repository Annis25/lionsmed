from django.urls import path
from . import views as v

app_name = "mailboxes"
urlpatterns = [
    path("messagerie/", v.home, name="home"),
    path("messagerie/<slug:slug>/", v.inbox, name="inbox"),
    path("messagerie/<slug:slug>/nouveau/", v.compose, name="compose"),
    path("messagerie/<slug:slug>/message/<uuid:email_id>/", v.message, name="message"),
    path("messagerie/<slug:slug>/message/<uuid:email_id>/non-lu/", v.unread, name="unread"),
    path("messagerie/<slug:slug>/envoyes/", v.sent, name="sent"),
    path("messagerie/<slug:slug>/envoyes/<uuid:outgoing_id>/", v.sent_detail, name="sent_detail"),
]
