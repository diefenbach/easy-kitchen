from django import template

from easy_kitchen.models import ShoppingList

register = template.Library()


@register.filter
def list_icon_class(value):
    """Bootstrap Icons class for a list icon, falling back to the basket."""
    return ShoppingList.ICON_CLASSES.get(value, ShoppingList.ICON_CLASSES[ShoppingList.Icon.BASKET])
