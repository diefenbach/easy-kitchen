from typing import Any

from django.utils.translation import gettext as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from easy_kitchen.models import Recipe, ShoppingList
from easy_kitchen.services import (
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
)
from .serializers import (
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


class ShoppingListViewSet(viewsets.ModelViewSet):
    """Shopping lists of the authenticated user, including reorder and JSON import."""

    serializer_class = ShoppingListSerializer

    def get_queryset(self):
        return ShoppingList.objects.filter(user=self.request.user).prefetch_related("items")

    @extend_schema(request=ReorderItemsSerializer, responses={200: ShoppingListSerializer})
    @action(detail=True, methods=["post"])
    def reorder(self, request, pk=None):
        shopping_list = self.get_object()
        try:
            reorder_items(shopping_list, [int(value) for value in request.data["item_ids"]])
        except (ValueError, KeyError, TypeError):
            return Response({"detail": _("Invalid order.")}, status=status.HTTP_400_BAD_REQUEST)
        shopping_list.refresh_from_db()
        return Response(self.get_serializer(shopping_list).data)

    @extend_schema(
        request=ReorderListsSerializer, responses={200: ShoppingListSerializer(many=True)}
    )
    @action(detail=False, methods=["post"], url_path="reorder")
    def reorder_lists(self, request):
        try:
            reorder_shopping_lists(request.user, [int(value) for value in request.data["list_ids"]])
        except (ValueError, KeyError, TypeError):
            return Response({"detail": _("Invalid order.")}, status=status.HTTP_400_BAD_REQUEST)
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


class RecipeViewSet(viewsets.ModelViewSet):
    """Recipes of the authenticated user, including reorder and JSON import."""

    serializer_class = RecipeSerializer

    def get_queryset(self):
        return Recipe.objects.filter(user=self.request.user).prefetch_related(
            "ingredients", "steps"
        )

    def _reorder(self, request, kind):
        recipe = self.get_object()
        try:
            reorder_recipe_lines(recipe, kind, [int(value) for value in request.data["line_ids"]])
        except (ValueError, KeyError, TypeError):
            return Response({"detail": _("Invalid order.")}, status=status.HTTP_400_BAD_REQUEST)
        recipe.refresh_from_db()
        return Response(self.get_serializer(recipe).data)

    @extend_schema(request=ReorderRecipesSerializer, responses={200: RecipeSerializer(many=True)})
    @action(detail=False, methods=["post"], url_path="reorder")
    def reorder_recipes(self, request):
        try:
            reorder_recipes(request.user, [int(value) for value in request.data["recipe_ids"]])
        except (ValueError, KeyError, TypeError):
            return Response({"detail": _("Invalid order.")}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(self.get_queryset(), many=True).data)

    @extend_schema(request=ReorderLinesSerializer, responses={200: RecipeSerializer})
    @action(detail=True, methods=["post"], url_path="reorder-ingredients")
    def reorder_ingredients(self, request, pk=None):
        return self._reorder(request, "ingredient")

    @extend_schema(request=ReorderLinesSerializer, responses={200: RecipeSerializer})
    @action(detail=True, methods=["post"], url_path="reorder-steps")
    def reorder_steps(self, request, pk=None):
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


class MealPlanViewSet(viewsets.GenericViewSet):
    """Weekly planning scoped to the authenticated user and addressed by date."""

    serializer_class = MealPlanDaySerializer
    lookup_field = "date"
    lookup_value_regex = r"\d{4}-\d{2}-\d{2}"

    @extend_schema(parameters=[MealPlanWeekQuerySerializer], responses=MealPlanWeekSerializer)
    def list(self, request):
        query = MealPlanWeekQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        try:
            data = meal_plan_week_data(request.user, query.validated_data.get("week"))
        except ValueError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(data)

    @extend_schema(
        parameters=[OpenApiParameter("date", OpenApiTypes.DATE, OpenApiParameter.PATH)],
        request=MealPlanAssignSerializer,
        responses=MealPlanDaySerializer,
    )
    def update(self, request, date=None):
        day = MealPlanDateSerializer(data={"date": date})
        day.is_valid(raise_exception=True)
        selection = MealPlanAssignSerializer(data=request.data)
        selection.is_valid(raise_exception=True)
        try:
            data = plan_owned_recipe(request.user, day.validated_data["date"], **selection.validated_data)
        except ValueError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(data)

    @extend_schema(
        parameters=[OpenApiParameter("date", OpenApiTypes.DATE, OpenApiParameter.PATH)],
        responses={204: None},
    )
    def destroy(self, request, date=None):
        day = MealPlanDateSerializer(data={"date": date})
        day.is_valid(raise_exception=True)
        clear_meal_plan_day(request.user, day.validated_data["date"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=MealPlanToListSerializer, responses=ShoppingListSerializer)
    @action(detail=False, methods=["post"], url_path="add-to-list")
    def add_to_list(self, request):
        selection = MealPlanToListSerializer(data=request.data)
        selection.is_valid(raise_exception=True)
        data = selection.validated_data
        try:
            target = add_meal_plan_to_owned_list(
                request.user,
                data["week"],
                list_id=data.get("shopping_list_id"),
                title=data.get("title", ""),
            )
        except ValueError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ShoppingListSerializer(target, context={"request": request}).data)
