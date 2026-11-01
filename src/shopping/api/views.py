from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from shopping.models import Recipe, ShoppingList
from shopping.services import (
    import_recipes,
    import_shopping_lists,
    reorder_items,
    reorder_recipe_lines,
    reorder_recipes,
    reorder_shopping_lists,
)
from .serializers import (
    RecipeSerializer,
    ReorderItemsSerializer,
    ReorderLinesSerializer,
    ReorderListsSerializer,
    ReorderRecipesSerializer,
    ShoppingListSerializer,
)


def _import_records(payload, key):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        records = payload.get(key)
        if isinstance(records, list):
            return records
    return None


class ShoppingListViewSet(viewsets.ModelViewSet):
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

    @extend_schema(request=ReorderListsSerializer, responses={200: ShoppingListSerializer(many=True)})
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
    serializer_class = RecipeSerializer

    def get_queryset(self):
        return Recipe.objects.filter(user=self.request.user).prefetch_related("ingredients", "steps")

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
                            "recipes": {"type": "array", "items": {"$ref": "#/components/schemas/Recipe"}}
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
        return Response(self.get_serializer(recipes, many=True).data, status=status.HTTP_201_CREATED)
