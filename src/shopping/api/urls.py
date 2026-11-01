from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny
from rest_framework.routers import DefaultRouter

from .views import RecipeViewSet, ShoppingListViewSet

router = DefaultRouter()
router.register("shopping-lists", ShoppingListViewSet, basename="shopping-list")
router.register("recipes", RecipeViewSet, basename="recipe")
resource_urls = [url for url in router.urls if url.name != "api-root"]
urlpatterns = [
    path("schema/", SpectacularAPIView.as_view(permission_classes=[AllowAny]), name="api-schema"),
    path("", SpectacularSwaggerView.as_view(url_name="api-schema", permission_classes=[AllowAny]), name="swagger-ui"),
    *resource_urls,
]
