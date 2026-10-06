from django.urls import path

from . import views

app_name = "notifications"
urlpatterns = [
    path("", views.inbox, name="inbox"),
    path("read-all/", views.mark_all_read, name="mark_all_read"),
    path("<uuid:pk>/open/", views.open_notification, name="open"),
]
