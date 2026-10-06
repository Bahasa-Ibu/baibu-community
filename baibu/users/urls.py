from django.urls import path

from . import views

app_name = "users"
urlpatterns = [
    path("account/", views.account_view, name="account"),
    path("account/complete/", views.complete_profile_view, name="complete_profile"),
    path("account/consent/", views.consent_view, name="consent"),
    path("account/delete/", views.account_deletion_view, name="account_deletion"),
]
