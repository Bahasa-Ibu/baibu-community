from django.urls import path

from . import views

app_name = "submissions"
urlpatterns = [
    path("", views.submission_list, name="list"),
    path("new/", views.submission_create, name="create"),
    path("<uuid:pk>/delete/", views.submission_delete, name="delete"),
]
