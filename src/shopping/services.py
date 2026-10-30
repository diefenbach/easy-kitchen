from django.db import transaction
from django.db.models import Max
from .models import ShoppingItem


def create_item(shopping_list, *, name, quantity="", checked=False, position=None):
    if position is None:
        position = (shopping_list.items.aggregate(last=Max("position"))["last"] or 0) + 1
    return ShoppingItem.objects.create(shopping_list=shopping_list, name=name, quantity=quantity, checked=checked, position=position)


@transaction.atomic
def reorder_items(shopping_list, item_ids):
    existing = set(shopping_list.items.filter(id__in=item_ids).values_list("id", flat=True))
    if existing != set(item_ids) or len(item_ids) != len(existing):
        raise ValueError("Ungültige Elementreihenfolge.")
    for position, item_id in enumerate(item_ids, start=1):
        ShoppingItem.objects.filter(pk=item_id, shopping_list=shopping_list).update(position=position)
