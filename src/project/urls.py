"""Root URLs: admin, allauth accounts, the REST API under /api/v1/, and the app. Media is served here
only with DEBUG.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("api/v1/", include("easy_kitchen.api.urls")),
    path("", include("easy_kitchen.urls")),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
