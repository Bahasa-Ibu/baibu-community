from django.urls import path

from . import views

app_name = "metrics"
urlpatterns = [
    path("", views.usage, name="usage"),
    path("export.csv", views.export, name="export"),
]
