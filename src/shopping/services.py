import re
from decimal import Decimal

from django.db import transaction
from django.db.models import Max
from django.utils.translation import gettext as _

_QUANTITY_AMOUNT = re.compile(r"^(\d+(?:[.,]\d+)?)\s*(.*)$")

from .models import ShoppingItem


def _normalized_name(name):
    return " ".join(name.split())


def _quantity_parts(quantity):
    return [part.strip() for part in (quantity or "").split(", ") if part.strip()]


def _format_amount(number, separator):
    if number == number.to_integral_value():
        return str(number.to_integral_value())
    text = format(number, "f").rstrip("0").rstrip(".")
    if separator == ",":
        text = text.replace(".", ",")
    return text


def _merge_quantities(*quantities):
    entries = []
    amounts = {}
    seen_text = set()
    for quantity in quantities:
        for part in _quantity_parts(quantity):
            match = _QUANTITY_AMOUNT.match(part)
            if match is None:
                key = part.casefold()
                if key in seen_text:
                    continue
                seen_text.add(key)
                entries.append(("text", part))
                continue
            number_text, unit = match.group(1), match.group(2).strip()
            unit_key = unit.casefold()
            number = Decimal(number_text.replace(",", "."))
            existing = amounts.get(unit_key)
            if existing is None:
                amounts[unit_key] = {
                    "total": number,
                    "unit": unit,
                    "separator": "," if "," in number_text else ".",
                }
                entries.append(("amount", unit_key))
            else:
                existing["total"] += number
    rendered = []
    for kind, value in entries:
        if kind == "text":
            rendered.append(value)
            continue
        amount = amounts[value]
        number = _format_amount(amount["total"], amount["separator"])
        rendered.append(f"{number} {amount['unit']}".strip())
    return ", ".join(rendered)


def create_item(shopping_list, *, name, quantity="", checked=False, position=None):
    name = _normalized_name(name)
    quantity = (quantity or "").strip()
    existing = next(
        (
            item
            for item in shopping_list.items.order_by("position", "id")
            if _normalized_name(item.name).casefold() == name.casefold()
        ),
        None,
    )
    if existing is not None:
        existing.quantity = _merge_quantities(existing.quantity, quantity)
        existing.checked = False
        existing.save(update_fields=["quantity", "checked", "updated_at"])
        return existing
    if position is None:
        position = (shopping_list.items.aggregate(last=Max("position"))["last"] or 0) + 1
    return ShoppingItem.objects.create(
        shopping_list=shopping_list,
        name=name,
        quantity=quantity,
        checked=checked,
        position=position,
    )


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
