import json

from django import forms
from django.core.validators import URLValidator
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError as DRFValidationError

from .api.serializers import RecipeSerializer, ShoppingListSerializer
from .models import Recipe, ShoppingItem, ShoppingList
from .services import _normalized_name, save_article


class ShoppingListForm(forms.ModelForm):
    """Edit a list title, icon, and date. A missing icon stays the basket."""

    class Meta:
        model = ShoppingList
        fields = ("title", "icon", "date")
        labels = {"icon": _("Icon")}
        widgets = {
            "icon": forms.RadioSelect(),
            "date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        }
        input_formats = {"date": ["%Y-%m-%d"]}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["icon"].required = False

    def clean_icon(self):
        """Keep a known icon and use the basket when the field was left empty."""
        icon = self.cleaned_data.get("icon")
        if icon in ShoppingList.Icon.values:
            return icon
        return ShoppingList.Icon.BASKET


class ShoppingItemForm(forms.ModelForm):
    """Edit an item name and quantity. The name field suggests saved articles."""

    class Meta:
        model = ShoppingItem
        fields = ("name", "quantity")
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "autocomplete": "off",
                    "role": "combobox",
                    "aria-autocomplete": "list",
                    "aria-expanded": "false",
                }
            )
        }


class ArticleForm(forms.Form):
    """Create or rename a saved article, rejecting a duplicate name for this user."""

    name = forms.CharField(label=_("Article"), max_length=255)

    def __init__(self, *args, user, instance=None, **kwargs):
        self.user = user
        self.instance = instance
        super().__init__(*args, **kwargs)

    def clean_name(self):
        """Normalize the name and reject a blank or duplicate article."""
        name = _normalized_name(self.cleaned_data["name"])
        if not name:
            raise forms.ValidationError(_("Enter an article name."))
        queryset = self.user.articles.all()
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.filter(name__iexact=name).exists():
            raise forms.ValidationError(_("An article with this name already exists."))
        return name

    def save(self):
        """Create the article, or rename the instance this form was given."""
        return save_article(self.user, self.cleaned_data["name"], article=self.instance)


_RECIPE_KEYS = {
    "ingredients",
    "steps",
    "description",
    "image_url",
    "calories",
    "protein",
    "preparation_minutes",
}
_LIST_KEYS = {"items", "date", "icon"}


def _import_kind(record):
    """Classify one record as a list or a recipe. Mixed signals and unknown records return None."""
    if not isinstance(record, dict):
        return None
    recipe = bool(_RECIPE_KEYS & record.keys())
    shopping_list = bool(_LIST_KEYS & record.keys())
    if recipe and shopping_list:
        return None
    if recipe or ("title" in record and not shopping_list):
        return "recipe"
    if shopping_list:
        return "list"
    return None


def _split_import_payload(payload):
    """Split wrapped or bare JSON into list and recipe records. A title alone is a recipe."""
    if isinstance(payload, dict) and {"lists", "recipes"} & payload.keys():
        lists = payload["lists"] if "lists" in payload else None
        recipes = payload["recipes"] if "recipes" in payload else None
        if lists is not None and not isinstance(lists, list):
            return None
        if recipes is not None and not isinstance(recipes, list):
            return None
        return lists, recipes

    records = [payload] if isinstance(payload, dict) else payload
    if not isinstance(records, list) or not records:
        return None
    lists, recipes = [], []
    for record in records:
        kind = _import_kind(record)
        if kind == "list":
            lists.append(record)
        elif kind == "recipe":
            recipes.append(record)
        else:
            return None
    return (lists or None), (recipes or None)


class ImportForm(forms.Form):
    """Accept JSON and split it into shopping lists and recipes."""

    json_data = forms.CharField(
        label=_("JSON"),
        widget=forms.Textarea(attrs={"class": "form-control font-monospace", "rows": 16}),
    )

    def clean_json_data(self):
        """Parse the JSON and validate each side with the API serializers."""
        try:
            payload = json.loads(self.cleaned_data["json_data"])
        except json.JSONDecodeError as error:
            raise forms.ValidationError(_("Enter valid JSON.")) from error

        split = _split_import_payload(payload)
        if split is None:
            raise forms.ValidationError(
                _("Could not tell whether this is a shopping list or a recipe.")
            )
        lists, recipes = split
        return {
            "lists": self._validate(ShoppingListSerializer, lists),
            "recipes": self._validate(RecipeSerializer, recipes),
        }

    def _validate(self, serializer_class, records):
        """Return validated records, or None when that side of the import was omitted."""
        if records is None:
            return None
        serializer = serializer_class(data=records, many=True)
        try:
            serializer.is_valid(raise_exception=True)
        except DRFValidationError as error:
            raise forms.ValidationError(
                _("The JSON does not match the EasyKitchen format.")
            ) from error
        return serializer.validated_data


class RecipeForm(forms.ModelForm):
    """Edit a recipe, including optional nutrition and an uploaded image or image URL."""

    image_url = forms.URLField(
        label=_("Image URL"),
        assume_scheme="https",
        required=False,
        max_length=500,
        validators=[URLValidator(schemes=["http", "https"])],
    )

    class Meta:
        model = Recipe
        fields = (
            "title",
            "description",
            "calories",
            "protein",
            "preparation_minutes",
            "image",
            "image_url",
        )
        labels = {
            "title": _("Title"),
            "description": _("Description"),
            "calories": _("Calories (kcal)"),
            "protein": _("Protein (g)"),
            "preparation_minutes": _("Preparation time (min)"),
            "image": _("Image"),
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "calories": forms.NumberInput(attrs={"min": 0}),
            "protein": forms.NumberInput(attrs={"min": 0}),
            "preparation_minutes": forms.NumberInput(attrs={"min": 0}),
        }


class RecipeLineForm(forms.Form):
    """Edit either an ingredient name and quantity or the text of a preparation step."""

    def __init__(self, *args, kind="ingredient", **kwargs):
        super().__init__(*args, **kwargs)
        if kind == "ingredient":
            self.fields["name"] = forms.CharField(label=_("Ingredient"), max_length=255)
            self.fields["quantity"] = forms.CharField(
                label=_("quantity"), max_length=100, required=False
            )
        else:
            self.fields["text"] = forms.CharField(
                label=_("Step"),
                max_length=2000,
                widget=forms.Textarea(attrs={"rows": 3}),
            )


class AddRecipeToListForm(forms.Form):
    """Choose one of the user's lists, or name a new list for the recipe's ingredients."""

    shopping_list = forms.ModelChoiceField(
        label=_("Shopping list"),
        queryset=ShoppingList.objects.none(),
        required=False,
        empty_label=_("Choose a list"),
    )
    title = forms.CharField(label=_("New list"), max_length=255, required=False)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["shopping_list"].queryset = ShoppingList.objects.filter(user=user)

    def clean(self):
        """Require an existing list or a title for a new one."""
        cleaned = super().clean()
        title = _normalized_name(cleaned.get("title") or "")
        cleaned["title"] = title
        if not title and not cleaned.get("shopping_list"):
            raise forms.ValidationError(_("Choose a list or enter a title for a new one."))
        return cleaned
