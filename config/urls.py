from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include
from django.urls import path
from django.views import defaults as default_views
from django.views.generic import TemplateView

from baibu.core import views as core_views

urlpatterns = [
    path("health/", core_views.health, name="health"),
    path("i18n/", include("django.conf.urls.i18n")),
]

# The default language has no URL prefix; other languages get /<code>/.
urlpatterns += i18n_patterns(
    path("", TemplateView.as_view(template_name="pages/home.html"), name="home"),
    path("privacy/", TemplateView.as_view(template_name="pages/privacy.html"), name="privacy"),
    path("terms/", TemplateView.as_view(template_name="pages/terms.html"), name="terms"),
    path("accounts/", include("allauth.urls")),
    path("users/", include("baibu.users.urls", namespace="users")),
    path("contribute/", include("baibu.submissions.urls", namespace="submissions")),
    path("chat/", include("baibu.chat.urls", namespace="chat")),
    path("notifications/", include("baibu.notifications.urls", namespace="notifications")),
    path("staff/", include("baibu.staff.urls", namespace="staff")),
    path("translations/", include("baibu.localization.urls", namespace="localization")),
    path(settings.ADMIN_URL, admin.site.urls),
    prefix_default_language=False,
)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += [
        path("400/", default_views.bad_request, kwargs={"exception": Exception("Bad Request!")}),
        path("403/", default_views.permission_denied, kwargs={"exception": Exception("Permission Denied")}),
        path("404/", default_views.page_not_found, kwargs={"exception": Exception("Page not Found")}),
        path("500/", default_views.server_error),
    ]
