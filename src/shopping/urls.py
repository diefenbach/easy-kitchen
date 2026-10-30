from django.urls import path
from . import views

app_name = "shopping"
urlpatterns = [
    path("", views.ShoppingListListView.as_view(), name="list"),
    path("listen/neu/", views.ShoppingListCreateView.as_view(), name="create"),
    path("listen/<int:pk>/", views.ShoppingListDetailView.as_view(), name="detail"),
    path("listen/<int:pk>/bearbeiten/", views.ShoppingListUpdateView.as_view(), name="update"),
    path("listen/<int:pk>/loeschen/", views.ShoppingListDeleteView.as_view(), name="delete"),
    path("listen/<int:list_pk>/items/", views.ItemCreateView.as_view(), name="item-create"),
    path("listen/<int:list_pk>/items/reihenfolge/", views.ItemReorderView.as_view(), name="item-reorder"),
    path("listen/<int:list_pk>/items/<int:pk>/", views.ItemUpdateView.as_view(), name="item-update"),
    path("listen/<int:list_pk>/items/<int:pk>/toggle/", views.ItemToggleView.as_view(), name="item-toggle"),
    path("listen/<int:list_pk>/items/<int:pk>/loeschen/", views.ItemDeleteView.as_view(), name="item-delete"),
]
