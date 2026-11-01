from django import template

from easy_kitchen.models import ShoppingList

register = template.Library()


@register.filter
def list_icon_class(value):
    return ShoppingList.ICON_CLASSES.get(value, ShoppingList.ICON_CLASSES[ShoppingList.Icon.BASKET])
