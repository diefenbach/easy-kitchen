from django.db import transaction
from django.db.models import Max
from django.utils.translation import gettext as _

from .models import ShoppingItem


def create_item(shopping_list, *, name, quantity="", checked=False, position=None):
    if position is None:
        position = (shopping_list.items.aggregate(last=Max("position"))["last"] or 0) + 1
    return ShoppingItem.objects.create(shopping_list=shopping_list, name=name, quantity=quantity, checked=checked, position=position)


def create_shopping_list(user, *, title, date, items=None):
    shopping_list = user.shopping_lists.create(title=title, date=date)
    for position, item_data in enumerate(items or [], start=1):
        item_data = dict(item_data)
        create_item(shopping_list, position=item_data.pop("position", position), **item_data)
    return shopping_list


@transaction.atomic
def import_shopping_lists(user, lists_data):
    return [create_shopping_list(user, **list_data) for list_data in lists_data]


@transaction.atomic
def reorder_items(shopping_list, item_ids):
    existing = set(shopping_list.items.filter(id__in=item_ids).values_list("id", flat=True))
    if existing != set(item_ids) or len(item_ids) != len(existing):
        raise ValueError(_("Invalid item order."))
    for position, item_id in enumerate(item_ids, start=1):
        ShoppingItem.objects.filter(pk=item_id, shopping_list=shopping_list).update(position=position)
