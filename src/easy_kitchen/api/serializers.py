from rest_framework import serializers
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from easy_kitchen.models import Department, Recipe, RecipeIngredient, RecipeStep, ShoppingItem, ShoppingList
from easy_kitchen.services import DepartmentResolutionError, create_item, create_recipe, create_shopping_list, resolve_department


class DepartmentSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source="__str__", read_only=True)

    class Meta:
        model = Department
        fields = ("id", "code", "name", "label")
        read_only_fields = fields


class DepartmentQuerySerializer(serializers.Serializer):
    query = serializers.CharField(max_length=255)


class ReorderItemsSerializer(serializers.Serializer):
    """Item ids in the order they should be saved."""

    item_ids = serializers.ListField(child=serializers.IntegerField())


class ReorderLinesSerializer(serializers.Serializer):
    """Ingredient or step ids in the order they should be saved."""

    line_ids = serializers.ListField(child=serializers.IntegerField())


class ReorderListsSerializer(serializers.Serializer):
    """Shopping-list ids in the order they should be saved."""

    list_ids = serializers.ListField(child=serializers.IntegerField())


class ReorderRecipesSerializer(serializers.Serializer):
    """Recipe ids in the order they should be saved."""

    recipe_ids = serializers.ListField(child=serializers.IntegerField())


class CompleteChildSerializer(serializers.ModelSerializer):
    """Supplied nested collections replace children, even during a root PATCH."""

    required_replacement_field = ""

    def validate(self, attrs):
        field = self.required_replacement_field
        if field not in attrs:
            raise serializers.ValidationError({field: self.fields[field].error_messages["required"]})
        return attrs


class ShoppingItemSerializer(CompleteChildSerializer):
    """One shopping-list line for the API."""

    required_replacement_field = "name"
    department = serializers.CharField(source="department_code", required=False, allow_blank=True, max_length=255)

    def validate_department(self, value):
        request = self.context.get("request")
        user = request.user if request else self.context.get("user")
        if not value:
            return ""
        if user is None:
            raise serializers.ValidationError(_("Invalid department."))
        try:
            department = resolve_department(user, value)
        except DepartmentResolutionError as error:
            raise serializers.ValidationError(error.as_dict()) from None
        return department.code if department else ""

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if "department_code" in attrs:
            attrs["department"] = attrs.pop("department_code")
        return attrs

    class Meta:
        model = ShoppingItem
        fields = ("id", "name", "quantity", "department", "checked", "position")
        read_only_fields = ("id",)


class ShoppingListSerializer(serializers.ModelSerializer):
    """A shopping list and its items. An omitted icon stays the basket."""

    items = ShoppingItemSerializer(many=True, required=False)
    icon = serializers.ChoiceField(choices=ShoppingList.Icon.choices, required=False)

    class Meta:
        model = ShoppingList
        fields = ("id", "title", "icon", "date", "position", "items", "created_at", "updated_at")
        read_only_fields = ("id", "position", "created_at", "updated_at")

    def create(self, validated_data):
        """Create the list and its items for the authenticated user."""
        return create_shopping_list(self.context["request"].user, **validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        """Update the list fields and replace its items when items were sent."""
        items = validated_data.pop("items", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items is not None:
            instance.items.all().delete()
            for position, item in enumerate(items, start=1):
                create_item(instance, position=item.pop("position", position), **item)
        return instance


class RecipeIngredientSerializer(CompleteChildSerializer):
    """One ingredient line for the API."""

    required_replacement_field = "name"

    class Meta:
        model = RecipeIngredient
        fields = ("id", "name", "quantity", "position")
        read_only_fields = ("id",)
        extra_kwargs = {
            "position": {"required": False},
            "quantity": {"required": False, "allow_blank": True},
        }


class RecipeStepSerializer(CompleteChildSerializer):
    """One preparation step for the API."""

    required_replacement_field = "text"

    text = serializers.CharField(max_length=2000)

    class Meta:
        model = RecipeStep
        fields = ("id", "text", "position")
        read_only_fields = ("id",)
        extra_kwargs = {"position": {"required": False}}


class RecipeSerializer(serializers.ModelSerializer):
    """A recipe with optional nutrition. Empty nutrition means the value is unknown."""

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
            "carbohydrates",
            "fat",
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
            "carbohydrates": {"required": False, "allow_null": True},
            "fat": {"required": False, "allow_null": True},
            "preparation_minutes": {"required": False, "allow_null": True},
        }

    def get_image(self, recipe):
        """Absolute URL of the uploaded image, or an empty string when there is none."""
        if not recipe.image:
            return ""
        return self._absolute(recipe.image.url)

    def get_picture_url(self, recipe):
        """Absolute URL of the uploaded image, otherwise the stored image URL."""
        if recipe.image:
            return self._absolute(recipe.image.url)
        return recipe.image_url

    def _absolute(self, url):
        """Build an absolute URL when the request is available."""
        request = self.context.get("request")
        if request is None:
            return url
        return request.build_absolute_uri(url)

    def create(self, validated_data):
        """Create the recipe for the authenticated user."""
        return create_recipe(self.context["request"].user, **self._recipe_data(validated_data))

    def update(self, instance, validated_data):
        """Update the recipe. Omitted ingredients and steps stay as they are."""
        data = self._recipe_data(validated_data, instance)
        return create_recipe(instance.user, recipe=instance, **data)

    def _recipe_data(self, validated_data, instance=None):
        """Keep omitted ingredients and steps unchanged when updating a recipe."""
        data = {
            "title": validated_data.get("title", instance.title if instance else ""),
            "description": validated_data.get(
                "description", instance.description if instance else ""
            ),
            "image_url": validated_data.get("image_url", instance.image_url if instance else ""),
            "calories": validated_data.get("calories", instance.calories if instance else None),
            "protein": validated_data.get("protein", instance.protein if instance else None),
            "carbohydrates": validated_data.get(
                "carbohydrates", instance.carbohydrates if instance else None
            ),
            "fat": validated_data.get("fat", instance.fat if instance else None),
            "preparation_minutes": validated_data.get(
                "preparation_minutes", instance.preparation_minutes if instance else None
            ),
        }
        if "ingredients" in validated_data:
            data["ingredients"] = validated_data["ingredients"]
        if "steps" in validated_data:
            data["steps"] = validated_data["steps"]
        return data


class MealPlanDateSerializer(serializers.Serializer):
    """A calendar date used to address a planner day."""

    date = serializers.DateField()


class MealPlanWeekQuerySerializer(serializers.Serializer):
    """An optional day in the requested week; omitted means the current local week."""

    week = serializers.DateField(required=False)


class MealPlanAssignSerializer(serializers.Serializer):
    """The owned recipe to assign to the day addressed by the URL."""

    recipe_id = serializers.IntegerField(min_value=1)


class MealPlanToListSerializer(serializers.Serializer):
    """A week and either an existing list id or a title for a new list."""

    week = serializers.DateField()
    shopping_list_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    title = serializers.CharField(max_length=255, required=False, allow_blank=True)


class PlannedRecipeSerializer(serializers.Serializer):
    """A planned recipe summary; full details are available from the recipes API."""

    id = serializers.IntegerField()
    title = serializers.CharField()


class MealPlanDaySerializer(serializers.Serializer):
    """One day, including empty days."""

    date = serializers.DateField()
    recipe = PlannedRecipeSerializer(allow_null=True)


class MealPlanWeekSerializer(serializers.Serializer):
    """A Monday–Sunday week with seven day records."""

    week_start = serializers.DateField()
    week_end = serializers.DateField()
    days = MealPlanDaySerializer(many=True)
