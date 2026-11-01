import re
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.db.models import Max
from django.utils.translation import gettext as _

_QUANTITY_AMOUNT = re.compile(r"^(\d+(?:[.,]\d+)?)\s*(.*)$")
_INGREDIENT_AMOUNT = r"\d+(?:[.,]\d+)?(?:/\d+)?(?:\s*[-–]\s*\d+(?:[.,]\d+)?)?"
_LEADING_INGREDIENT = re.compile(
    rf"^(?P<amount>{_INGREDIENT_AMOUNT})(?:\s+(?P<second>\S+))?(?:\s+(?P<rest>.+))?$"
)
_TRAILING_INGREDIENT = re.compile(
    rf"^(?P<name>.+?)\s+(?P<amount>{_INGREDIENT_AMOUNT})(?:\s+(?P<unit>\S+))?$"
)

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


def _merge_quantities(quantity_entries):
    entries = []
    amounts = {}
    seen_text = set()
    for part in quantity_entries:
        part = part.strip()
        if not part:
            continue
        text_key = part.casefold()
        match = _QUANTITY_AMOUNT.match(part)
        if match is None:
            if text_key in seen_text:
                continue
            seen_text.add(text_key)
            entries.append(("text", part))
            continue
        number_text, unit = match.group(1), match.group(2).strip()
        number = Decimal(number_text.replace(",", "."))
        normalized_unit = unit.casefold().rstrip(".")
        key = normalized_unit
        existing = amounts.get(key)
        if existing is None:
            amounts[key] = {
                "total": number,
                "unit": unit,
                "separator": "," if "," in number_text else ".",
            }
            entries.append(("amount", key))
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


def remember_article(user, name):
    name = _normalized_name(name)
    if not name:
        return None
    existing = user.articles.filter(name__iexact=name).order_by("id").first()
    if existing is not None:
        return existing
    return user.articles.create(name=name)


def save_article(user, name, article=None):
    name = _normalized_name(name)
    if article is None:
        return user.articles.create(name=name)
    article.name = name
    article.save(update_fields=["name", "updated_at"])
    return article


def create_item(shopping_list, *, name, quantity="", checked=False, position=None):
    name = _normalized_name(name)
    quantity = (quantity or "").strip()
    remember_article(shopping_list.user, name)
    existing = next(
        (
            item
            for item in shopping_list.items.order_by("position", "id")
            if _normalized_name(item.name).casefold() == name.casefold()
        ),
        None,
    )
    if existing is not None:
        quantity_entries = _quantity_parts(existing.quantity)
        if quantity:
            quantity_entries.append(quantity)
        existing.quantity = _merge_quantities(quantity_entries)
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


def _line_text(line):
    if isinstance(line, str):
        return _normalized_name(line)
    return _normalized_name(line.get("text") or "")


def _write_lines(manager, lines):
    manager.all().delete()
    for index, line in enumerate(lines or [], start=1):
        text = _line_text(line)
        if not text:
            continue
        position = index if isinstance(line, str) else (line.get("position") or index)
        manager.create(text=text, position=position)


def _write_ingredients(manager, ingredients):
    manager.all().delete()
    for index, line in enumerate(ingredients or [], start=1):
        name = _normalized_name(line.get("name") or "")
        quantity = (line.get("quantity") or "").strip()
        if not name:
            continue
        position = line.get("position") or index
        manager.create(name=name, quantity=quantity, position=position)


def _clean_image_url(image_url):
    image_url = (image_url or "").strip()
    if not image_url:
        return ""
    try:
        URLValidator(schemes=["http", "https"])(image_url)
    except ValidationError as error:
        raise ValueError(_("Enter a valid image URL.")) from error
    return image_url


def create_recipe(user, *, title, description="", image_url="", ingredients=None, steps=None, recipe=None):
    title = _normalized_name(title)
    if not title:
        raise ValueError(_("Enter a title."))
    description = (description or "").strip()
    image_url = _clean_image_url(image_url)
    if recipe is None:
        recipe = user.recipes.create(title=title, description=description, image_url=image_url)
    else:
        recipe.title = title
        recipe.description = description
        recipe.image_url = image_url
        recipe.save(update_fields=["title", "description", "image_url", "updated_at"])
    if ingredients is not None:
        _write_ingredients(recipe.ingredients, ingredients)
    if steps is not None:
        _write_lines(recipe.steps, steps)
    return recipe


@transaction.atomic
def import_recipes(user, recipes_data):
    return [create_recipe(user, **recipe_data) for recipe_data in recipes_data]


def add_recipe_line(recipe, kind, text="", name="", quantity=""):
    manager = _recipe_lines(recipe, kind)
    position = (manager.aggregate(last=Max("position"))["last"] or 0) + 1
    if kind == "ingredient":
        return manager.create(name=_normalized_name(name), quantity=(quantity or "").strip(), position=position)
    return manager.create(text=_normalized_name(text), position=position)


def reorder_recipe_lines(recipe, kind, line_ids):
    manager = _recipe_lines(recipe, kind)
    model = manager.model
    _reorder(manager, line_ids, model, "recipe", recipe)


def _ingredient_name_and_quantity(text):
    text = _normalized_name(text)
    leading = _LEADING_INGREDIENT.match(text)
    if leading:
        amount, second, rest = leading.group("amount"), leading.group("second"), leading.group("rest")
        if second and rest and len(second) <= 4:
            return _normalized_name(rest), f"{amount} {second}"
        if second and rest:
            return _normalized_name(f"{second} {rest}"), amount
        if second:
            return second, amount
        return text, ""
    trailing = _TRAILING_INGREDIENT.match(text)
    if trailing and not trailing.group("name")[:1].isdigit():
        name, amount, unit = trailing.group("name"), trailing.group("amount"), trailing.group("unit")
        if unit and len(unit) <= 4:
            return _normalized_name(name), f"{amount} {unit}"
        if unit:
            return _normalized_name(f"{name} {unit}"), amount
        return _normalized_name(name), amount
    return text, ""


def add_recipe_ingredients_to_list(recipe, shopping_list):
    if shopping_list.user_id != recipe.user_id:
        raise ValueError(_("Invalid shopping list."))
    for ingredient in recipe.ingredients.all():
        create_item(shopping_list, name=ingredient.name, quantity=ingredient.quantity)
    return shopping_list


def _recipe_lines(recipe, kind):
    if kind == "ingredient":
        return recipe.ingredients
    if kind == "step":
        return recipe.steps
    raise ValueError(_("Invalid order."))


def _reorder(manager, ordered_ids, model, parent_field, parent):
    existing = set(manager.filter(id__in=ordered_ids).values_list("id", flat=True))
    if existing != set(ordered_ids) or len(ordered_ids) != len(existing):
        raise ValueError(_("Invalid order."))
    for position, line_id in enumerate(ordered_ids, start=1):
        model.objects.filter(pk=line_id, **{parent_field: parent}).update(position=position)
