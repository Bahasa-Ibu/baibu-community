from django.urls import path

from . import views

app_name = "localization"
urlpatterns = [
    path("", views.index, name="index"),
    path("sources/update/", views.update_sources, name="update_sources"),
    path("<str:language_code>/", views.catalogue, name="catalogue"),
    path("<str:language_code>/plural-forms/", views.plural_forms, name="plural_forms"),
    path("<str:language_code>/upload/", views.upload, name="upload"),
    path("<str:language_code>/download/", views.download, name="download"),
    path("<str:language_code>/publish/", views.publish, name="publish"),
    path("<str:language_code>/history/", views.history, name="history"),
    path("<str:language_code>/history/<uuid:pk>/restore/", views.restore, name="restore"),
]
