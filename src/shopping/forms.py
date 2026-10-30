from django import forms
from .models import ShoppingItem, ShoppingList


class ShoppingListForm(forms.ModelForm):
    class Meta:
        model = ShoppingList
        fields = ("title", "date")
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}


class ShoppingItemForm(forms.ModelForm):
    class Meta:
        model = ShoppingItem
        fields = ("name", "quantity")
