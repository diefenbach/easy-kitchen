import json

from django import forms
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError as DRFValidationError

from .api.serializers import ShoppingListSerializer
from .models import ShoppingItem, ShoppingList
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
            raise forms.ValidationError(_("The JSON does not match the EasyList format.")) from error
        return serializer.validated_data
