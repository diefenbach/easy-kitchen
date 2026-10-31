from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from shopping.models import ShoppingList
from shopping.services import import_shopping_lists, reorder_items
from .serializers import ReorderItemsSerializer, ShoppingListSerializer


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
        payload = request.data
        records = payload.get("lists", payload if isinstance(payload, list) else None)
        if not isinstance(records, list):
            return Response(
                {"detail": _("Expected a list or {'lists': [...]}.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = self.get_serializer(data=records, many=True)
        serializer.is_valid(raise_exception=True)
        lists = import_shopping_lists(request.user, serializer.validated_data)
        return Response(self.get_serializer(lists, many=True).data, status=status.HTTP_201_CREATED)
