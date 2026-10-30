from rest_framework.routers import DefaultRouter
from .views import ShoppingListViewSet

router = DefaultRouter()
router.register("shopping-lists", ShoppingListViewSet, basename="shopping-list")
urlpatterns = router.urls
