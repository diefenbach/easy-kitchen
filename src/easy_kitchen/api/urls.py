from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny
from rest_framework.routers import DefaultRouter

from .views import ArticleViewSet, DepartmentViewSet, MealPlanViewSet, RecipeViewSet, ShoppingItemViewSet, ShoppingListViewSet

router = DefaultRouter()
router.register("departments", DepartmentViewSet, basename="department")
router.register("articles", ArticleViewSet, basename="article")
router.register("shopping-items", ShoppingItemViewSet, basename="shopping-item")
router.register("shopping-lists", ShoppingListViewSet, basename="shopping-list")
router.register("recipes", RecipeViewSet, basename="recipe")
router.register("meal-planner", MealPlanViewSet, basename="meal-plan")
resource_urls = [url for url in router.urls if url.name != "api-root"]
urlpatterns = [
    path("schema/", SpectacularAPIView.as_view(permission_classes=[AllowAny]), name="api-schema"),
    path("", SpectacularSwaggerView.as_view(url_name="api-schema", permission_classes=[AllowAny]), name="swagger-ui"),
    *resource_urls,
]
