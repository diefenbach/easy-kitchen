from rest_framework import serializers
from shopping.models import ShoppingItem, ShoppingList
from shopping.services import create_shopping_list


class ShoppingItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShoppingItem
        fields = ("id", "name", "quantity", "checked", "position")
        read_only_fields = ("id",)


class ShoppingListSerializer(serializers.ModelSerializer):
    items = ShoppingItemSerializer(many=True, required=False)

    class Meta:
        model = ShoppingList
        fields = ("id", "title", "date", "items", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def create(self, validated_data):
        return create_shopping_list(self.context["request"].user, **validated_data)

    def update(self, instance, validated_data):
        items = validated_data.pop("items", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items is not None:
            instance.items.all().delete()
            for position, item in enumerate(items, start=1):
                create_item(instance, position=item.pop("position", position), **item)
        return instance
