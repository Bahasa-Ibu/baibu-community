from django.urls import path

from . import views

app_name = "chat"
urlpatterns = [
    path("", views.home, name="home"),
    path("consent/", views.consent_view, name="consent"),
    path("new/", views.new_conversation, name="new"),
    path("<uuid:pk>/", views.conversation_view, name="conversation"),
    path("<uuid:pk>/messages/", views.messages_view, name="messages"),
    path("<uuid:pk>/send/", views.send_view, name="send"),
    path("<uuid:pk>/delete/", views.delete_view, name="delete"),
    path("runs/<uuid:run_id>/retry/", views.retry_view, name="retry"),
    path("replies/<uuid:message_id>/report/", views.report_view, name="report"),
    path("voice/", views.new_voice_view, name="voice_new"),
    path("<uuid:pk>/voice/", views.voice_view, name="voice"),
    path("audio/<uuid:clip_id>/", views.audio_view, name="audio"),
    path("audio/<uuid:clip_id>/retry/", views.retry_voice_view, name="voice_retry"),
]
