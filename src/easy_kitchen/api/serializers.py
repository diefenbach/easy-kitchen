from rest_framework import serializers
from easy_kitchen.models import Recipe, RecipeIngredient, RecipeStep, ShoppingItem, ShoppingList
from easy_kitchen.services import create_item, create_recipe, create_shopping_list


class ReorderItemsSerializer(serializers.Serializer):
    item_ids = serializers.ListField(child=serializers.IntegerField())


class ReorderLinesSerializer(serializers.Serializer):
    line_ids = serializers.ListField(child=serializers.IntegerField())


class ReorderListsSerializer(serializers.Serializer):
    list_ids = serializers.ListField(child=serializers.IntegerField())


class ReorderRecipesSerializer(serializers.Serializer):
    recipe_ids = serializers.ListField(child=serializers.IntegerField())


class ShoppingItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShoppingItem
        fields = ("id", "name", "quantity", "checked", "position")
        read_only_fields = ("id",)


class ShoppingListSerializer(serializers.ModelSerializer):
    items = ShoppingItemSerializer(many=True, required=False)

    class Meta:
        model = ShoppingList
        fields = ("id", "title", "date", "position", "items", "created_at", "updated_at")
        read_only_fields = ("id", "position", "created_at", "updated_at")

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


class RecipeIngredientSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecipeIngredient
        fields = ("id", "name", "quantity", "position")
        read_only_fields = ("id",)
        extra_kwargs = {"position": {"required": False}, "quantity": {"required": False, "allow_blank": True}}


class RecipeStepSerializer(serializers.ModelSerializer):
    text = serializers.CharField(max_length=2000)

    class Meta:
        model = RecipeStep
        fields = ("id", "text", "position")
        read_only_fields = ("id",)
        extra_kwargs = {"position": {"required": False}}


class RecipeSerializer(serializers.ModelSerializer):
    ingredients = RecipeIngredientSerializer(many=True, required=False)
    steps = RecipeStepSerializer(many=True, required=False)
    image = serializers.SerializerMethodField()
    picture_url = serializers.SerializerMethodField()

    class Meta:
        model = Recipe
        fields = (
            "id",
            "title",
            "description",
            "image",
            "image_url",
            "picture_url",
            "calories",
            "protein",
            "preparation_minutes",
            "position",
            "ingredients",
            "steps",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "position", "created_at", "updated_at")
        extra_kwargs = {
            "calories": {"required": False, "allow_null": True},
            "protein": {"required": False, "allow_null": True},
            "preparation_minutes": {"required": False, "allow_null": True},
        }

    def get_image(self, recipe):
        if not recipe.image:
            return ""
        return self._absolute(recipe.image.url)

    def get_picture_url(self, recipe):
        if recipe.image:
            return self._absolute(recipe.image.url)
        return recipe.image_url

    def _absolute(self, url):
        request = self.context.get("request")
        if request is None:
            return url
        return request.build_absolute_uri(url)

    def create(self, validated_data):
        return create_recipe(self.context["request"].user, **self._recipe_data(validated_data))

    def update(self, instance, validated_data):
        data = self._recipe_data(validated_data, instance)
        return create_recipe(instance.user, recipe=instance, **data)

    def _recipe_data(self, validated_data, instance=None):
        data = {
            "title": validated_data.get("title", instance.title if instance else ""),
            "description": validated_data.get("description", instance.description if instance else ""),
            "image_url": validated_data.get("image_url", instance.image_url if instance else ""),
            "calories": validated_data.get("calories", instance.calories if instance else None),
            "protein": validated_data.get("protein", instance.protein if instance else None),
            "preparation_minutes": validated_data.get(
                "preparation_minutes", instance.preparation_minutes if instance else None
            ),
        }
        if "ingredients" in validated_data:
            data["ingredients"] = validated_data["ingredients"]
        if "steps" in validated_data:
            data["steps"] = validated_data["steps"]
        return data
