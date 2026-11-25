"""REST API viewsets. Every endpoint needs a Bearer token or a session and only sees the
authenticated user's records.

Writes go through easy_kitchen.services, so the API and MCP share their rules and error codes.
"""

from typing import Any

from django.utils.translation import gettext as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from easy_kitchen.authentication import signed_in_user
from easy_kitchen.errors import ObjectNotFoundError, ServiceError
from easy_kitchen.models import Article, Department, Recipe, ShoppingItem, ShoppingList
from easy_kitchen.services import (
    DepartmentResolutionError,
    department_data,
    list_department_data,
    resolve_department,
    add_meal_plan_to_owned_list,
    clear_meal_plan_day,
    meal_plan_week_data,
    plan_owned_recipe,
    import_recipes,
    import_shopping_lists,
    reorder_items,
    reorder_recipe_lines,
    reorder_recipes,
    reorder_shopping_lists,
    set_owned_recipe_favorite,
    delete_owned_shopping_item,
    delete_completed_items_from_owned_list,
    add_item_to_owned_list,
    add_recipe_to_owned_list,
    delete_owned_recipe,
    delete_owned_shopping_list,
    query_owned_recipes,
    query_owned_shopping_lists,
    query_owned_shopping_items,
    query_owned_articles,
)
from .serializers import (
    DepartmentSerializer,
    ArticleSerializer,
    ShoppingItemUpdateSerializer,
    RecipeFavoriteSerializer,
    AddShoppingItemSerializer,
    AddRecipeToListSerializer,
    DeletedItemsSerializer,
    DepartmentQuerySerializer,
    MealPlanAssignSerializer,
    MealPlanDateSerializer,
    MealPlanDaySerializer,
    MealPlanToListSerializer,
    MealPlanWeekQuerySerializer,
    MealPlanWeekSerializer,
    RecipeSerializer,
    ReorderItemsSerializer,
    ReorderLinesSerializer,
    ReorderListsSerializer,
    ReorderRecipesSerializer,
    ShoppingListSerializer,
    CollectionQuerySerializer,
    RecipeListQuerySerializer,
    ShoppingListQuerySerializer,
    ShoppingItemQuerySerializer,
    ArticleListQuerySerializer,
)


def _import_records(payload: Any, key: str) -> list[Any] | None:
    """Accept a bare list or an object whose key holds the records."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        records = payload.get(key)
        if isinstance(records, list):
            return records
    return None


def _collection_response(view, request, query_serializer, operation):
    selection = query_serializer(data=request.query_params)
    selection.is_valid(raise_exception=True)
    values = selection.validated_data
    records = operation(request.user, **values)
    context = {**view.get_serializer_context(), "summary": values.get("summary", False)}
    return Response(view.get_serializer(records, many=True, context=context).data)


class ServiceErrorsMixin(APIView):
    """Translate shared business errors once, keeping field details and stable codes."""

    def handle_exception(self, exc):
        """Answer ServiceError as 400 (404 for missing objects) with its stable code; add `code` to
        DRF's own errors too.
        """
        if isinstance(exc, ServiceError):
            detail = exc.as_dict()
            data: dict[str, object] = {"code": exc.code, "detail": str(exc)}
            if isinstance(exc, DepartmentResolutionError):
                data["department"] = detail
            elif exc.field:
                data[exc.field] = str(exc)
            return Response(data, status=404 if isinstance(exc, ObjectNotFoundError) else 400)
        response = super().handle_exception(exc)
        if isinstance(response.data, dict):
            code = {401: "unauthorized", 403: "forbidden", 404: "not_found"}.get(response.status_code, "invalid_input")
            response.data.setdefault("code", code)
        else:
            response.data = {"code": "invalid_input", "errors": response.data}
        return response


class DepartmentViewSet(ServiceErrorsMixin, mixins.UpdateModelMixin, viewsets.ReadOnlyModelViewSet):
    """Read, resolve and rename departments without changing their stable codes."""

    serializer_class = DepartmentSerializer

    def get_queryset(self):
        """Return the user's departments (none while the OpenAPI schema is generated)."""
        if getattr(self, "swagger_fake_view", False):
            return Department.objects.none()
        return signed_in_user(self.request).departments.all()

    @extend_schema(parameters=[CollectionQuerySerializer], responses=DepartmentSerializer(many=True))
    def list(self, request):
        """Return one page of the user's departments, filtered by ?q=."""
        selection = CollectionQuerySerializer(data=request.query_params)
        selection.is_valid(raise_exception=True)
        return Response(list_department_data(request.user, **selection.validated_data))

    @extend_schema(parameters=[DepartmentQuerySerializer], responses={200: DepartmentSerializer, 400: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["get"])
    def resolve(self, request):
        """Resolve ?query= (code, name, or translation) to one department, or answer 400 with
        candidates to choose from.
        """
        query = DepartmentQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        department = resolve_department(request.user, query.validated_data["query"])
        if department is None:  # only for a blank query, which DepartmentQuerySerializer already rejects
            raise ValidationError({"query": [_("Enter a department name.")]})
        return Response(department_data(department))


class ShoppingItemViewSet(ServiceErrorsMixin, mixins.DestroyModelMixin, mixins.UpdateModelMixin, viewsets.ReadOnlyModelViewSet):
    """Items on the user's lists: list, read, update, delete."""

    serializer_class = ShoppingItemUpdateSerializer

    @extend_schema(parameters=[ShoppingItemQuerySerializer], responses=ShoppingItemUpdateSerializer(many=True))
    def list(self, request):
        """Return one page of items, filtered by ?q=, ?checked=, and ?list_id=."""
        return _collection_response(self, request, ShoppingItemQuerySerializer, query_owned_shopping_items)

    def get_queryset(self):
        """Return the items on the user's lists (none while the OpenAPI schema is generated)."""
        if getattr(self, "swagger_fake_view", False):
            return ShoppingItem.objects.none()
        return ShoppingItem.objects.filter(shopping_list__user=self.request.user).select_related("department")

    def perform_destroy(self, instance):
        """Delete the item through the shared service."""
        delete_owned_shopping_item(signed_in_user(self.request), item_id=instance.pk)


class ArticleViewSet(ServiceErrorsMixin, mixins.UpdateModelMixin, viewsets.ReadOnlyModelViewSet):
    """The user's saved articles: list, read, update."""

    serializer_class = ArticleSerializer

    @extend_schema(parameters=[ArticleListQuerySerializer], responses=ArticleSerializer(many=True))
    def list(self, request):
        """Return one page of articles, filtered by ?q= and ?department=."""
        return _collection_response(self, request, ArticleListQuerySerializer, query_owned_articles)

    def get_queryset(self):
        """Return the user's articles (none while the OpenAPI schema is generated)."""
        if getattr(self, "swagger_fake_view", False):
            return Article.objects.none()
        return Article.objects.filter(user=self.request.user).select_related("department")


class ShoppingListViewSet(ServiceErrorsMixin, viewsets.ModelViewSet):
    """Shopping lists of the authenticated user, including reorder and JSON import."""

    serializer_class = ShoppingListSerializer

    @extend_schema(parameters=[ShoppingListQuerySerializer], responses=ShoppingListSerializer(many=True))
    def list(self, request):
        """Return one page of lists, filtered by ?q=, ?date_from=, and ?date_to=; ?summary=true
        omits the items.
        """
        return _collection_response(self, request, ShoppingListQuerySerializer, query_owned_shopping_lists)

    def get_queryset(self):
        """Return the user's lists with their items."""
        return ShoppingList.objects.filter(user=self.request.user).prefetch_related("items__department")

    def perform_destroy(self, instance):
        """Delete the list through the shared service."""
        delete_owned_shopping_list(signed_in_user(self.request), list_id=instance.pk)

    @extend_schema(request=AddShoppingItemSerializer, responses={200: ShoppingItemUpdateSerializer})
    @action(detail=True, methods=["post"], url_path="add-item")
    def add_item(self, request, pk=None):
        """Add an item to the list, merging it into an item of the same name."""
        shopping_list = self.get_object()
        serializer = AddShoppingItemSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        item = add_item_to_owned_list(request.user, list_id=shopping_list.pk, **serializer.validated_data)
        return Response(ShoppingItemUpdateSerializer(item).data)

    @extend_schema(request=None, responses={200: DeletedItemsSerializer})
    @action(detail=True, methods=["post"], url_path="delete-completed")
    def delete_completed(self, request, pk=None):
        """Delete the list's checked items and return how many were deleted."""
        shopping_list = self.get_object()
        count = delete_completed_items_from_owned_list(request.user, list_id=shopping_list.pk)
        return Response({"list_id": shopping_list.pk, "deleted_count": count})

    @extend_schema(request=ReorderItemsSerializer, responses={200: ShoppingListSerializer})
    @action(detail=True, methods=["post"])
    def reorder(self, request, pk=None):
        """Set the order of the list's items; `item_ids` must be exactly the list's items."""
        shopping_list = self.get_object()
        selection = ReorderItemsSerializer(data=request.data)
        selection.is_valid(raise_exception=True)
        reorder_items(shopping_list, selection.validated_data["item_ids"])
        shopping_list.refresh_from_db()
        return Response(self.get_serializer(shopping_list).data)

    @extend_schema(
        request=ReorderListsSerializer, responses={200: ShoppingListSerializer(many=True)}
    )
    @action(detail=False, methods=["post"], url_path="reorder")
    def reorder_lists(self, request):
        """Set the order of the user's lists; `list_ids` must be exactly the user's lists."""
        selection = ReorderListsSerializer(data=request.data)
        selection.is_valid(raise_exception=True)
        reorder_shopping_lists(request.user, selection.validated_data["list_ids"])
        return Response(self.get_serializer(self.get_queryset(), many=True).data)

    @extend_schema(
        request={
            "application/json": {
                "oneOf": [
                    {"type": "array", "items": {"$ref": "#/components/schemas/ShoppingList"}},
                    {
                        "type": "object",
                        "required": ["lists"],
                        "properties": {
                            "lists": {
                                "type": "array",
                                "items": {"$ref": "#/components/schemas/ShoppingList"},
                            }
                        },
                    },
                ]
            }
        },
        responses={201: ShoppingListSerializer(many=True)},
    )
    @action(detail=False, methods=["post"])
    def import_json(self, request):
        """Import lists from `[...]` or `{"lists": [...]}`, all or nothing; they are placed first.
        """
        records = _import_records(request.data, "lists")
        if not isinstance(records, list):
            return Response(
                {"detail": _("Expected a list or {'lists': [...]}.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = self.get_serializer(data=records, many=True)
        serializer.is_valid(raise_exception=True)
        lists = import_shopping_lists(request.user, serializer.validated_data)
        return Response(self.get_serializer(lists, many=True).data, status=status.HTTP_201_CREATED)


class RecipeViewSet(ServiceErrorsMixin, viewsets.ModelViewSet):
    """Recipes of the authenticated user, including reorder and JSON import."""

    serializer_class = RecipeSerializer

    @extend_schema(parameters=[RecipeListQuerySerializer], responses=RecipeSerializer(many=True))
    def list(self, request):
        """Return one page of recipes, filtered by ?q= and ?is_favorite=; ?summary=true omits
        ingredients and steps.
        """
        return _collection_response(self, request, RecipeListQuerySerializer, query_owned_recipes)

    def get_queryset(self):
        """Return the user's recipes with ingredients and steps."""
        return Recipe.objects.filter(user=self.request.user).prefetch_related(
            "ingredients", "steps"
        )

    def perform_destroy(self, instance):
        """Delete the recipe through the shared service."""
        delete_owned_recipe(signed_in_user(self.request), recipe_id=instance.pk)

    @extend_schema(request=AddRecipeToListSerializer, responses={200: ShoppingListSerializer})
    @action(detail=True, methods=["post"], url_path="add-to-list")
    def add_to_list(self, request, pk=None):
        """Add the recipe's ingredients to an existing list or a new one and return that list."""
        recipe = self.get_object()
        serializer = AddRecipeToListSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        shopping_list = add_recipe_to_owned_list(request.user, recipe_id=recipe.pk, **data)
        return Response(ShoppingListSerializer(shopping_list, context={"request": request}).data)

    @extend_schema(request=RecipeFavoriteSerializer, responses={200: RecipeSerializer})
    @action(detail=True, methods=["post"])
    def favorite(self, request, pk=None):
        """Mark or unmark the recipe as favourite."""
        recipe = self.get_object()
        serializer = RecipeFavoriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        recipe = set_owned_recipe_favorite(request.user, recipe_id=recipe.pk, **serializer.validated_data)
        return Response(self.get_serializer(recipe).data)

    def _reorder(self, request, kind):
        recipe = self.get_object()
        selection = ReorderLinesSerializer(data=request.data)
        selection.is_valid(raise_exception=True)
        reorder_recipe_lines(recipe, kind, selection.validated_data["line_ids"])
        recipe.refresh_from_db()
        return Response(self.get_serializer(recipe).data)

    @extend_schema(request=ReorderRecipesSerializer, responses={200: RecipeSerializer(many=True)})
    @action(detail=False, methods=["post"], url_path="reorder")
    def reorder_recipes(self, request):
        """Set the order of the user's recipes; `recipe_ids` must be exactly the user's recipes.
        """
        selection = ReorderRecipesSerializer(data=request.data)
        selection.is_valid(raise_exception=True)
        reorder_recipes(request.user, selection.validated_data["recipe_ids"])
        return Response(self.get_serializer(self.get_queryset(), many=True).data)

    @extend_schema(request=ReorderLinesSerializer, responses={200: RecipeSerializer})
    @action(detail=True, methods=["post"], url_path="reorder-ingredients")
    def reorder_ingredients(self, request, pk=None):
        """Set the order of the recipe's ingredients."""
        return self._reorder(request, "ingredient")

    @extend_schema(request=ReorderLinesSerializer, responses={200: RecipeSerializer})
    @action(detail=True, methods=["post"], url_path="reorder-steps")
    def reorder_steps(self, request, pk=None):
        """Set the order of the recipe's steps."""
        return self._reorder(request, "step")

    @extend_schema(
        request={
            "application/json": {
                "oneOf": [
                    {"type": "array", "items": {"$ref": "#/components/schemas/Recipe"}},
                    {
                        "type": "object",
                        "required": ["recipes"],
                        "properties": {
                            "recipes": {
                                "type": "array",
                                "items": {"$ref": "#/components/schemas/Recipe"},
                            }
                        },
                    },
                ]
            }
        },
        responses={201: RecipeSerializer(many=True)},
    )
    @action(detail=False, methods=["post"])
    def import_json(self, request):
        """Import recipes from `[...]` or `{"recipes": [...]}`, all or nothing; they are placed
        first.
        """
        records = _import_records(request.data, "recipes")
        if not isinstance(records, list):
            return Response(
                {"detail": _("Expected a list or {'recipes': [...]}.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = self.get_serializer(data=records, many=True)
        serializer.is_valid(raise_exception=True)
        recipes = import_recipes(request.user, serializer.validated_data)
        return Response(
            self.get_serializer(recipes, many=True).data, status=status.HTTP_201_CREATED
        )


class MealPlanViewSet(ServiceErrorsMixin, viewsets.GenericViewSet):
    """Weekly planning scoped to the authenticated user and addressed by date."""

    serializer_class = MealPlanDaySerializer
    lookup_field = "date"
    lookup_value_regex = r"\d{4}-\d{2}-\d{2}"

    @extend_schema(parameters=[MealPlanWeekQuerySerializer], responses=MealPlanWeekSerializer)
    def list(self, request):
        """Return the planned recipes of the week containing ?week= (default: this week)."""
        query = MealPlanWeekQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = meal_plan_week_data(request.user, query.validated_data.get("week"))
        return Response(data)

    @extend_schema(
        parameters=[OpenApiParameter("date", OpenApiTypes.DATE, OpenApiParameter.PATH)],
        request=MealPlanAssignSerializer,
        responses=MealPlanDaySerializer,
    )
    def update(self, request, date=None):
        """Plan a recipe for the date in the URL, replacing that day's recipe."""
        day = MealPlanDateSerializer(data={"date": date})
        day.is_valid(raise_exception=True)
        selection = MealPlanAssignSerializer(data=request.data)
        selection.is_valid(raise_exception=True)
        data = plan_owned_recipe(request.user, day.validated_data["date"], **selection.validated_data)
        return Response(data)

    @extend_schema(
        parameters=[OpenApiParameter("date", OpenApiTypes.DATE, OpenApiParameter.PATH)],
        responses={204: None},
    )
    def destroy(self, request, date=None):
        """Remove the planned recipe for the date in the URL."""
        day = MealPlanDateSerializer(data={"date": date})
        day.is_valid(raise_exception=True)
        clear_meal_plan_day(request.user, day.validated_data["date"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=MealPlanToListSerializer, responses=ShoppingListSerializer)
    @action(detail=False, methods=["post"], url_path="add-to-list")
    def add_to_list(self, request):
        """Add the ingredients of every recipe planned in `week` to an existing or a new list."""
        selection = MealPlanToListSerializer(data=request.data)
        selection.is_valid(raise_exception=True)
        data = selection.validated_data
        target = add_meal_plan_to_owned_list(
            request.user, data["week"], list_id=data.get("shopping_list_id"), title=data.get("title", ""),
        )
        return Response(ShoppingListSerializer(target, context={"request": request}).data)
