import json

from django import forms
from django.core.validators import URLValidator
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError as DRFValidationError

from .api.serializers import ShoppingListSerializer
from .models import Recipe, ShoppingItem, ShoppingList
from .services import _normalized_name, save_article


class ShoppingListForm(forms.ModelForm):
    class Meta:
        model = ShoppingList
        fields = ("title", "date")
        widgets = {"date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})}
        input_formats = {"date": ["%Y-%m-%d"]}


class ShoppingItemForm(forms.ModelForm):
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
    name = forms.CharField(label=_("Article"), max_length=255)

    def __init__(self, *args, user, instance=None, **kwargs):
        self.user = user
        self.instance = instance
        super().__init__(*args, **kwargs)

    def clean_name(self):
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
        return save_article(self.user, self.cleaned_data["name"], article=self.instance)


class ShoppingListImportForm(forms.Form):
    json_data = forms.CharField(
        label=_("Shopping-list JSON"),
        widget=forms.Textarea(attrs={"class": "form-control font-monospace", "rows": 16}),
    )

    def clean_json_data(self):
        try:
            payload = json.loads(self.cleaned_data["json_data"])
        except json.JSONDecodeError as error:
            raise forms.ValidationError(_("Enter valid JSON.")) from error

        records = payload.get("lists") if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            raise forms.ValidationError(_("Expected a list or an object with a 'lists' array."))

        serializer = ShoppingListSerializer(data=records, many=True)
        try:
            serializer.is_valid(raise_exception=True)
        except DRFValidationError as error:
            raise forms.ValidationError(_("The JSON does not match the EasyKitchen format.")) from error
        return serializer.validated_data


class RecipeForm(forms.ModelForm):
    image_url = forms.URLField(
        label=_("Image URL"),
        assume_scheme="https",
        required=False,
        max_length=500,
        validators=[URLValidator(schemes=["http", "https"])],
    )

    class Meta:
        model = Recipe
        fields = ("title", "description", "calories", "protein", "preparation_minutes", "image", "image_url")
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
    def __init__(self, *args, kind="ingredient", **kwargs):
        super().__init__(*args, **kwargs)
        if kind == "ingredient":
            self.fields["name"] = forms.CharField(label=_("Ingredient"), max_length=255)
            self.fields["quantity"] = forms.CharField(label=_("quantity"), max_length=100, required=False)
        else:
            self.fields["text"] = forms.CharField(
                label=_("Step"),
                max_length=2000,
                widget=forms.Textarea(attrs={"rows": 3}),
            )


class AddRecipeToListForm(forms.Form):
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
        cleaned = super().clean()
        title = _normalized_name(cleaned.get("title") or "")
        cleaned["title"] = title
        if not title and not cleaned.get("shopping_list"):
            raise forms.ValidationError(_("Choose a list or enter a title for a new one."))
        return cleaned


class RecipeImportForm(forms.Form):
    json_data = forms.CharField(
        label=_("Recipe JSON"),
        widget=forms.Textarea(attrs={"class": "form-control font-monospace", "rows": 16}),
    )

    def clean_json_data(self):
        from .api.serializers import RecipeSerializer

        try:
            payload = json.loads(self.cleaned_data["json_data"])
        except json.JSONDecodeError as error:
            raise forms.ValidationError(_("Enter valid JSON.")) from error

        records = payload.get("recipes") if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            raise forms.ValidationError(_("Expected a list or an object with a 'recipes' array."))

        serializer = RecipeSerializer(data=records, many=True)
        try:
            serializer.is_valid(raise_exception=True)
        except DRFValidationError as error:
            raise forms.ValidationError(_("The JSON does not match the EasyKitchen format.")) from error
        return serializer.validated_data
