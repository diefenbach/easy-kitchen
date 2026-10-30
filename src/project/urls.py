from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("i18n/", include("django.conf.urls.i18n")),
    path("api/v1/", include("shopping.api.urls")),
    path("", include("shopping.urls")),
]
