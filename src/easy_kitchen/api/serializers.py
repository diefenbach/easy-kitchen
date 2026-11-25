"""DRF serializers for the REST API; writes go through easy_kitchen.services."""

# drf-stubs declare `ModelSerializer.Meta`, so every serializer's own `class Meta` reads as an incompatible
# override; that is how DRF is meant to be used.
# pyright: reportIncompatibleVariableOverride=false

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


class StrictInputMixin(serializers.Serializer):
    """Reject attempts to write unknown or read-only fields on update endpoints."""

    def to_internal_value(self, data):
        """Reject input naming a field that does not exist or is read-only, then validate as usual.
        """
        if not isinstance(data, Mapping):
            return super().to_internal_value(data)
        allowed = {name for name, field in self.fields.items() if not field.read_only}
        if set(data) - allowed:
            raise serializers.ValidationError({"non_field_errors": [_("Unsupported update field.")]})
        return super().to_internal_value(data)


def _department_code(serializer: serializers.Serializer, value: str) -> str:
    """Resolve a department name or code for the request's user; return its code, or "" for none.

    Raises a ValidationError with the resolver's candidates when the department is unknown or ambiguous.
    """
    request = serializer.context.get("request")
    user = request.user if request else serializer.context.get("user")
    if not value:
        return ""
    if user is None:
        raise serializers.ValidationError(_("Invalid department."))
    try:
        department = resolve_department(user, value)
    except DepartmentResolutionError as error:
        raise serializers.ValidationError(error.as_dict()) from None
    return department.code if department else ""


class StrictUpdateSerializer(StrictInputMixin, serializers.ModelSerializer):
    """Model serializer that rejects unknown and read-only fields."""

    pass


class StrictSerializer(StrictInputMixin, serializers.Serializer):
    """Plain serializer that rejects unknown and read-only fields."""

    pass


class WholeNumberField(serializers.IntegerField):
    """Integer field with the same rules as the services: 0 to COUNT_LIMIT, no fractions or
    booleans.
    """

    def to_internal_value(self, data):
        """Return the whole number; an empty string or an invalid value is a validation error."""
        if data == "":
            self.fail("invalid")
        try:
            number = clean_count(data)
        except ServiceError as error:
            raise serializers.ValidationError(str(error), code=error.code) from None
        if number is None:
            self.fail("invalid")
        return number


class StrictBooleanField(serializers.BooleanField):
    """Boolean field that accepts only JSON true and false, not strings or numbers."""

    def to_internal_value(self, data):
        """Return the value when it is a real boolean; anything else is a validation error."""
        if not isinstance(data, bool):
            self.fail("invalid", input=data)
        return data


class CollectionQuerySerializer(StrictSerializer):
    """Query parameters every collection accepts: search words `q`, `limit`, and `offset`."""

    q = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    limit = serializers.IntegerField(min_value=1, max_value=MAX_LIST_LIMIT, default=DEFAULT_LIST_LIMIT)
    offset = serializers.IntegerField(min_value=0, max_value=COUNT_LIMIT, default=0)


class OptionalQueryBooleanField(serializers.BooleanField):
    # Query parameters are optional filters, not unchecked HTML form checkboxes.
    """Boolean query filter that stays unset when the parameter is missing."""

    default_empty_html = empty


class RecipeListQuerySerializer(CollectionQuerySerializer):
    """Query parameters of GET /recipes/."""

    is_favorite = OptionalQueryBooleanField(required=False)
    summary = serializers.BooleanField(default=False)


class ShoppingListQuerySerializer(CollectionQuerySerializer):
    """Query parameters of GET /shopping-lists/."""

    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    summary = serializers.BooleanField(default=False)


class ShoppingItemQuerySerializer(CollectionQuerySerializer):
    """Query parameters of GET /shopping-items/."""

    checked = OptionalQueryBooleanField(required=False)
    list_id = serializers.IntegerField(min_value=1, required=False)


class ArticleListQuerySerializer(CollectionQuerySerializer):
    """Query parameters of GET /articles/."""

    department = serializers.CharField(max_length=255, required=False, allow_blank=True)


class DepartmentSerializer(StrictUpdateSerializer):
    # A field named like Field.label; DRF's metaclass moves declared fields off the class, so they never clash.
    """A department; only the name can be changed."""

    label = serializers.CharField(source="__str__", read_only=True)  # pyright: ignore[reportAssignmentType]

    class Meta:
        model = Department
        fields = ("id", "code", "name", "label")
        read_only_fields = ("id", "code", "label")

    def update(self, instance, validated_data):
        """Rename the department through the shared service."""
        return update_owned_department(self.context["request"].user, department_id=instance.pk, changes=validated_data)


class DepartmentQuerySerializer(StrictSerializer):
    """Query parameter of GET /departments/resolve/."""

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
        """Require the replacement field, so a replaced child is never saved half empty."""
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
        """Resolve the department name or code to the user's department code."""
        return _department_code(self, value)

    def validate(self, attrs):
        """Hand the resolved department on under the model's field name."""
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
        """Hand the resolved department on under the model's field name."""
        if "department_code" in attrs:
            attrs["department"] = attrs.pop("department_code")
        return attrs

    def to_representation(self, instance):
        """Return the item in the shared JSON shape."""
        return item_data(instance)

    def update(self, instance, validated_data):
        """Update the item through the shared service."""
        return update_owned_shopping_item(self.context["request"].user, item_id=instance.pk, changes=validated_data)


class ArticleSerializer(StrictUpdateSerializer):
    """A saved article: name and department code."""

    department = serializers.CharField(source="department_code", required=False, allow_blank=True, max_length=255)
    validate_department = ShoppingItemSerializer.validate_department

    class Meta:
        model = Article
        fields = ("id", "name", "department")
        read_only_fields = ("id",)
        # The service applies the same case-insensitive uniqueness rules as the web editor.
        validators = []

    def to_representation(self, instance):
        """Return the article in the shared JSON shape."""
        return article_data(instance)

    def update(self, instance, validated_data):
        """Update the article through the shared service."""
        if "department_code" in validated_data:
            validated_data["department"] = validated_data.pop("department_code")
        return update_owned_article(self.context["request"].user, article_id=instance.pk, changes=validated_data)


class RecipeFavoriteSerializer(StrictSerializer):
    """Body of POST /recipes/{id}/favorite/."""

    is_favorite = StrictBooleanField()


class AddShoppingItemSerializer(StrictSerializer):
    """Body of POST /shopping-lists/{id}/add_item/."""

    name = serializers.CharField(max_length=255)
    quantity = serializers.CharField(max_length=100, required=False, allow_blank=True)
    department = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    def validate_department(self, value):
        """Resolve the department; null keeps the article's default."""
        if value is None:
            return None
        return _department_code(self, value)


class AddRecipeToListSerializer(StrictSerializer):
    """Body of POST /recipes/{id}/add_to_list/: an existing list id or a title for a new list."""

    list_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    list_title = serializers.CharField(max_length=255, required=False, allow_blank=True)


class DeletedItemsSerializer(StrictSerializer):
    """Response of POST /shopping-lists/{id}/delete_completed/."""

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
        """Return the list in the shared JSON shape; summary omits the items."""
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
        """Return the recipe in the shared JSON shape with an absolute picture URL; summary omits
        ingredients and steps.
        """
        return recipe_data(instance, absolute_url=self._absolute, summary=self.context.get("summary", False))

    def update(self, instance, validated_data):
        """Update the recipe through the shared service."""
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
