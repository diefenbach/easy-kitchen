import json

from django import forms
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError as DRFValidationError

from .api.serializers import ShoppingListSerializer
from .models import ShoppingItem, ShoppingList


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
