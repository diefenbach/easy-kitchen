from collections.abc import Mapping

from rest_framework import serializers
from rest_framework.fields import empty
from django.utils.translation import gettext_lazy as _
from easy_kitchen.errors import ServiceError
from easy_kitchen.presenters import recipe_data, shopping_list_data, item_data, article_data
from easy_kitchen.validation import DESCRIPTION_LIMIT, COUNT_LIMIT, DEFAULT_LIST_LIMIT, MAX_LIST_LIMIT, clean_count
from easy_kitchen.models import Article, Department, Recipe, RecipeIngredient, RecipeStep, ShoppingItem, ShoppingList
from easy_kitchen.services import (
    DepartmentResolutionError, create_recipe, create_shopping_list, resolve_department,
    update_owned_article, update_owned_department, update_owned_shopping_item,
    update_owned_shopping_list, update_owned_recipe,
)


class StrictInputMixin:
    """Reject attempts to write unknown or read-only fields on update endpoints."""

    def to_internal_value(self, data):
        if not isinstance(data, Mapping):
            return super().to_internal_value(data)
        allowed = {name for name, field in self.fields.items() if not field.read_only}
        if set(data) - allowed:
            raise serializers.ValidationError({"non_field_errors": [_("Unsupported update field.")]})
        return super().to_internal_value(data)


class StrictUpdateSerializer(StrictInputMixin, serializers.ModelSerializer):
    pass


class StrictSerializer(StrictInputMixin, serializers.Serializer):
    pass


class WholeNumberField(serializers.IntegerField):
    def to_internal_value(self, value):
        if value == "":
            self.fail("invalid")
        try:
            return clean_count(value)
        except ServiceError as error:
            raise serializers.ValidationError(str(error), code=error.code) from None


class StrictBooleanField(serializers.BooleanField):
    def to_internal_value(self, value):
        if not isinstance(value, bool):
            self.fail("invalid", input=value)
        return value


class CollectionQuerySerializer(StrictSerializer):
    q = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    limit = serializers.IntegerField(min_value=1, max_value=MAX_LIST_LIMIT, default=DEFAULT_LIST_LIMIT)
    offset = serializers.IntegerField(min_value=0, max_value=COUNT_LIMIT, default=0)


class OptionalQueryBooleanField(serializers.BooleanField):
    # Query parameters are optional filters, not unchecked HTML form checkboxes.
    default_empty_html = empty


class RecipeListQuerySerializer(CollectionQuerySerializer):
    is_favorite = OptionalQueryBooleanField(required=False)
    summary = serializers.BooleanField(default=False)


class ShoppingListQuerySerializer(CollectionQuerySerializer):
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    summary = serializers.BooleanField(default=False)


class ShoppingItemQuerySerializer(CollectionQuerySerializer):
    checked = OptionalQueryBooleanField(required=False)
    list_id = serializers.IntegerField(min_value=1, required=False)


class ArticleListQuerySerializer(CollectionQuerySerializer):
    department = serializers.CharField(max_length=255, required=False, allow_blank=True)


class DepartmentSerializer(StrictUpdateSerializer):
    label = serializers.CharField(source="__str__", read_only=True)

    class Meta:
        model = Department
        fields = ("id", "code", "name", "label")
        read_only_fields = ("id", "code", "label")

    def update(self, instance, validated_data):
        return update_owned_department(self.context["request"].user, department_id=instance.pk, changes=validated_data)


class DepartmentQuerySerializer(StrictSerializer):
    query = serializers.CharField(max_length=255)


class ReorderItemsSerializer(StrictSerializer):
    """Item ids in the order they should be saved."""

    item_ids = serializers.ListField(child=serializers.IntegerField())


class ReorderLinesSerializer(StrictSerializer):
    """Ingredient or step ids in the order they should be saved."""

    line_ids = serializers.ListField(child=serializers.IntegerField())


class ReorderListsSerializer(StrictSerializer):
    """Shopping-list ids in the order they should be saved."""

    list_ids = serializers.ListField(child=serializers.IntegerField())


class ReorderRecipesSerializer(StrictSerializer):
    """Recipe ids in the order they should be saved."""

    recipe_ids = serializers.ListField(child=serializers.IntegerField())


class CompleteChildSerializer(StrictUpdateSerializer):
    """Supplied nested collections replace children, even during a root PATCH."""

    required_replacement_field = ""
    position = WholeNumberField(required=False, min_value=0, max_value=COUNT_LIMIT)

    def validate(self, attrs):
        field = self.required_replacement_field
        if field not in attrs:
            raise serializers.ValidationError({field: self.fields[field].error_messages["required"]})
        return attrs


class ShoppingItemSerializer(CompleteChildSerializer):
    """One shopping-list line for the API."""

    required_replacement_field = "name"
    checked = StrictBooleanField(required=False)
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


class ShoppingItemUpdateSerializer(StrictUpdateSerializer):
    """A single item PATCH preserves omitted fields and never replaces other items."""

    department = serializers.CharField(source="department_code", required=False, allow_blank=True, max_length=255)
    list_id = serializers.IntegerField(source="shopping_list_id", read_only=True)
    checked = StrictBooleanField(required=False)
    validate_department = ShoppingItemSerializer.validate_department

    class Meta:
        model = ShoppingItem
        fields = ("id", "list_id", "name", "quantity", "department", "checked", "position")
        read_only_fields = ("id", "list_id", "position")

    def validate(self, attrs):
        if "department_code" in attrs:
            attrs["department"] = attrs.pop("department_code")
        return attrs

    def to_representation(self, instance):
        return item_data(instance)

    def update(self, instance, validated_data):
        return update_owned_shopping_item(self.context["request"].user, item_id=instance.pk, changes=validated_data)


class ArticleSerializer(StrictUpdateSerializer):
    department = serializers.CharField(source="department_code", required=False, allow_blank=True, max_length=255)
    validate_department = ShoppingItemSerializer.validate_department

    class Meta:
        model = Article
        fields = ("id", "name", "department")
        read_only_fields = ("id",)
        # The service applies the same case-insensitive uniqueness rules as the web editor.
        validators = []

    def to_representation(self, instance):
        return article_data(instance)

    def update(self, instance, validated_data):
        if "department_code" in validated_data:
            validated_data["department"] = validated_data.pop("department_code")
        return update_owned_article(self.context["request"].user, article_id=instance.pk, changes=validated_data)


class RecipeFavoriteSerializer(StrictSerializer):
    is_favorite = StrictBooleanField()


class AddShoppingItemSerializer(StrictSerializer):
    name = serializers.CharField(max_length=255)
    quantity = serializers.CharField(max_length=100, required=False, allow_blank=True)
    department = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    def validate_department(self, value):
        if value is None:
            return None
        return ShoppingItemSerializer.validate_department(self, value)


class AddRecipeToListSerializer(StrictSerializer):
    list_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    list_title = serializers.CharField(max_length=255, required=False, allow_blank=True)


class DeletedItemsSerializer(StrictSerializer):
    list_id = serializers.IntegerField()
    deleted_count = serializers.IntegerField(min_value=0)


class ShoppingListSerializer(StrictUpdateSerializer):
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

    def to_representation(self, instance):
        return shopping_list_data(instance, summary=self.context.get("summary", False))

    def update(self, instance, validated_data):
        """Update the list fields and replace its items when items were sent."""
        return update_owned_shopping_list(self.context["request"].user, list_id=instance.pk, changes=validated_data)


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


class RecipeSerializer(StrictUpdateSerializer):
    """A recipe with optional nutrition. Empty nutrition means the value is unknown."""

    description = serializers.CharField(max_length=DESCRIPTION_LIMIT, required=False, allow_blank=True)
    calories = WholeNumberField(required=False, allow_null=True, min_value=0, max_value=COUNT_LIMIT)
    protein = WholeNumberField(required=False, allow_null=True, min_value=0, max_value=COUNT_LIMIT)
    carbohydrates = WholeNumberField(required=False, allow_null=True, min_value=0, max_value=COUNT_LIMIT)
    fat = WholeNumberField(required=False, allow_null=True, min_value=0, max_value=COUNT_LIMIT)
    preparation_minutes = WholeNumberField(required=False, allow_null=True, min_value=0, max_value=COUNT_LIMIT)

    ingredients = RecipeIngredientSerializer(many=True, required=False)
    steps = RecipeStepSerializer(many=True, required=False)
    picture_url = serializers.URLField(read_only=True, allow_blank=True)

    class Meta:
        model = Recipe
        fields = (
            "id",
            "title",
            "is_favorite",
            "description",
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
        read_only_fields = ("id", "is_favorite", "position", "created_at", "updated_at")
        extra_kwargs = {"image_url": {"write_only": True}}

    def _absolute(self, url):
        """Build an absolute URL when the request is available."""
        request = self.context.get("request")
        if request is None:
            return url
        return request.build_absolute_uri(url)

    def create(self, validated_data):
        """Create the recipe for the authenticated user."""
        return create_recipe(self.context["request"].user, **validated_data)

    def to_representation(self, instance):
        return recipe_data(instance, absolute_url=self._absolute, summary=self.context.get("summary", False))

    def update(self, instance, validated_data):
        return update_owned_recipe(self.context["request"].user, recipe_id=instance.pk, changes=validated_data)


class MealPlanDateSerializer(StrictSerializer):
    """A calendar date used to address a planner day."""

    date = serializers.DateField()


class MealPlanWeekQuerySerializer(StrictSerializer):
    """An optional day in the requested week; omitted means the current local week."""

    week = serializers.DateField(required=False)


class MealPlanAssignSerializer(StrictSerializer):
    """The owned recipe to assign to the day addressed by the URL."""

    recipe_id = serializers.IntegerField(min_value=1)


class MealPlanToListSerializer(StrictSerializer):
    """A week and either an existing list id or a title for a new list."""

    week = serializers.DateField()
    shopping_list_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    title = serializers.CharField(max_length=255, required=False, allow_blank=True)


class PlannedRecipeSerializer(StrictSerializer):
    """A planned recipe summary; full details are available from the recipes API."""

    id = serializers.IntegerField()
    title = serializers.CharField()


class MealPlanDaySerializer(StrictSerializer):
    """One day, including empty days."""

    date = serializers.DateField()
    recipe = PlannedRecipeSerializer(allow_null=True)


class MealPlanWeekSerializer(StrictSerializer):
    """A Monday–Sunday week with seven day records."""

    week_start = serializers.DateField()
    week_end = serializers.DateField()
    days = MealPlanDaySerializer(many=True)
