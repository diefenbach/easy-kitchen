from django.urls import path
from . import views

app_name = "shopping"
urlpatterns = [
    path("", views.ShoppingListListView.as_view(), name="list"),
    path("articles/", views.ArticleListView.as_view(), name="articles"),
    path("articles/<int:pk>/", views.ArticleUpdateView.as_view(), name="article-update"),
    path("articles/<int:pk>/delete/", views.ArticleDeleteView.as_view(), name="article-delete"),
    path("lists/new/", views.ShoppingListCreateView.as_view(), name="create"),
    path("lists/import/", views.ShoppingListImportView.as_view(), name="import-json"),
    path("lists/<int:pk>/", views.ShoppingListDetailView.as_view(), name="detail"),
    path("lists/<int:pk>/edit/", views.ShoppingListUpdateView.as_view(), name="update"),
    path("lists/<int:pk>/delete/", views.ShoppingListDeleteView.as_view(), name="delete"),
    path("lists/<int:list_pk>/items/", views.ItemCreateView.as_view(), name="item-create"),
    path(
        "lists/<int:list_pk>/items/reset/",
        views.ItemsResetCheckedView.as_view(),
        name="items-reset-checked",
    ),
    path(
        "lists/<int:list_pk>/items/reorder/",
        views.ItemReorderView.as_view(),
        name="item-reorder",
    ),
    path("lists/<int:list_pk>/items/<int:pk>/", views.ItemUpdateView.as_view(), name="item-update"),
    path(
        "lists/<int:list_pk>/items/<int:pk>/toggle/",
        views.ItemToggleView.as_view(),
        name="item-toggle",
    ),
    path(
        "lists/<int:list_pk>/items/<int:pk>/delete/",
        views.ItemDeleteView.as_view(),
        name="item-delete",
    ),
]
