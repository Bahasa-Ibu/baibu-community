from django.urls import path

from . import views

app_name = "staff"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("review/submissions/", views.submission_queue, name="submissions"),
    path("review/submissions/<uuid:pk>/", views.submission_detail, name="submission"),
    path("review/chats/", views.flag_queue, name="flags"),
    path("review/chats/<uuid:pk>/", views.flag_detail, name="flag"),
    path("errors/", views.errors, name="errors"),
]
