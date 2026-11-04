from django.urls import path
from . import planner_views, recipe_views, views

app_name = "easy_kitchen"
urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("lists/", views.ShoppingListListView.as_view(), name="list"),
    path("planner/", planner_views.MealPlanView.as_view(), name="planner"),
    path("planner/assign/", planner_views.MealPlanAssignView.as_view(), name="planner-assign"),
    path(
        "planner/<str:day>/clear/",
        planner_views.MealPlanClearView.as_view(),
        name="planner-clear",
    ),
    path(
        "planner/add-to-list/",
        planner_views.MealPlanAddToListView.as_view(),
        name="planner-add-to-list",
    ),
    path("recipes/", recipe_views.RecipeListView.as_view(), name="recipes"),
    path("recipes/reorder/", recipe_views.RecipeReorderView.as_view(), name="recipe-reorder"),
    path("recipes/new/", recipe_views.RecipeCreateView.as_view(), name="recipe-create"),
    path("import/", views.ImportView.as_view(), name="import-json"),
    path("export/", views.ExportView.as_view(), name="export-json"),
    path("recipes/<int:pk>/", recipe_views.RecipeDetailView.as_view(), name="recipe-detail"),
    path("recipes/<int:pk>/pdf/", recipe_views.RecipePdfView.as_view(), name="recipe-pdf"),
    path("recipes/<int:pk>/edit/", recipe_views.RecipeUpdateView.as_view(), name="recipe-update"),
    path("recipes/<int:pk>/delete/", recipe_views.RecipeDeleteView.as_view(), name="recipe-delete"),
    path("recipes/<int:pk>/add-to-list/", recipe_views.RecipeAddToListView.as_view(), name="recipe-add-to-list"),
    path(
        "recipes/<int:recipe_pk>/ingredients/",
        recipe_views.IngredientCreateView.as_view(),
        name="recipe-ingredient-create",
    ),
    path(
        "recipes/<int:recipe_pk>/ingredients/reorder/",
        recipe_views.IngredientReorderView.as_view(),
        name="recipe-ingredient-reorder",
    ),
    path(
        "recipes/<int:recipe_pk>/ingredients/<int:pk>/",
        recipe_views.IngredientUpdateView.as_view(),
        name="recipe-ingredient-update",
    ),
    path(
        "recipes/<int:recipe_pk>/ingredients/<int:pk>/delete/",
        recipe_views.IngredientDeleteView.as_view(),
        name="recipe-ingredient-delete",
    ),
    path(
        "recipes/<int:recipe_pk>/steps/",
        recipe_views.StepCreateView.as_view(),
        name="recipe-step-create",
    ),
    path(
        "recipes/<int:recipe_pk>/steps/reorder/",
        recipe_views.StepReorderView.as_view(),
        name="recipe-step-reorder",
    ),
    path(
        "recipes/<int:recipe_pk>/steps/<int:pk>/",
        recipe_views.StepUpdateView.as_view(),
        name="recipe-step-update",
    ),
    path(
        "recipes/<int:recipe_pk>/steps/<int:pk>/delete/",
        recipe_views.StepDeleteView.as_view(),
        name="recipe-step-delete",
    ),
    path("articles/", views.ArticleListView.as_view(), name="articles"),
    path("articles/<int:pk>/", views.ArticleUpdateView.as_view(), name="article-update"),
    path("articles/<int:pk>/delete/", views.ArticleDeleteView.as_view(), name="article-delete"),
    path("lists/reorder/", views.ShoppingListReorderView.as_view(), name="list-reorder"),
    path("lists/new/", views.ShoppingListCreateView.as_view(), name="create"),
    path("lists/<int:pk>/", views.ShoppingListDetailView.as_view(), name="detail"),
    path(
        "lists/<int:pk>/hide-completed/",
        views.ListHideCompletedView.as_view(),
        name="list-hide-completed",
    ),
    path("lists/<int:pk>/edit/", views.ShoppingListUpdateView.as_view(), name="update"),
    path("lists/<int:pk>/delete/", views.ShoppingListDeleteView.as_view(), name="delete"),
    path("lists/<int:list_pk>/items/", views.ItemCreateView.as_view(), name="item-create"),
    path(
        "lists/<int:list_pk>/items/delete-completed/",
        views.ItemsDeleteCompletedView.as_view(),
        name="items-delete-completed",
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
