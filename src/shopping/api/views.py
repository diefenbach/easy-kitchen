from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from shopping.models import ShoppingList
from shopping.services import reorder_items
from .serializers import ShoppingItemSerializer, ShoppingListSerializer


class ShoppingListViewSet(viewsets.ModelViewSet):
    serializer_class = ShoppingListSerializer

    def get_queryset(self):
        return ShoppingList.objects.filter(user=self.request.user).prefetch_related("items")

    @action(detail=True, methods=["post"])
    def reorder(self, request, pk=None):
        shopping_list = self.get_object()
        try:
            reorder_items(shopping_list, [int(value) for value in request.data["item_ids"]])
        except (ValueError, KeyError, TypeError):
            return Response({"detail": "Ungültige Reihenfolge."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(shopping_list).data)

    @action(detail=False, methods=["post"])
    def import_json(self, request):
        payload = request.data
        records = payload.get("lists", payload if isinstance(payload, list) else None)
        if not isinstance(records, list):
            return Response({"detail": "Erwartet wird eine Liste oder {'lists': [...]}."}, status=status.HTTP_400_BAD_REQUEST)
        serializer = self.get_serializer(data=records, many=True)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            lists = serializer.save()
        return Response(self.get_serializer(lists, many=True).data, status=status.HTTP_201_CREATED)
