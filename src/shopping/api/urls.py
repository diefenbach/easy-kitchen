from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from .views import ShoppingListViewSet

router = DefaultRouter()
router.register("shopping-lists", ShoppingListViewSet, basename="shopping-list")
resource_urls = [url for url in router.urls if url.name != "api-root"]
urlpatterns = [
    path("schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path("", SpectacularSwaggerView.as_view(url_name="api-schema"), name="swagger-ui"),
    *resource_urls,
]
