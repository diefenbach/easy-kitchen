import re
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.db.models import F, Manager, Max, Model
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import Article, Recipe, RecipeIngredient, RecipeStep, ShoppingItem, ShoppingList

_QUANTITY_AMOUNT = re.compile(r"^(\d+(?:[.,]\d+)?)\s*(.*)$")
_INGREDIENT_AMOUNT = r"\d+(?:[.,]\d+)?(?:/\d+)?(?:\s*[-–]\s*\d+(?:[.,]\d+)?)?"
_LEADING_INGREDIENT = re.compile(
    rf"^(?P<amount>{_INGREDIENT_AMOUNT})(?:\s+(?P<second>\S+))?(?:\s+(?P<rest>.+))?$"
)
_TRAILING_INGREDIENT = re.compile(
    rf"^(?P<name>.+?)\s+(?P<amount>{_INGREDIENT_AMOUNT})(?:\s+(?P<unit>\S+))?$"
)


def _normalized_name(name: str) -> str:
    """Collapse whitespace so names compare and store consistently."""
    return " ".join(name.split())


def _quantity_parts(quantity: str) -> list[str]:
    """Split a stored quantity on ', ' into the pieces that can be merged."""
    return [part.strip() for part in (quantity or "").split(", ") if part.strip()]


def _format_amount(number: Decimal, separator: str) -> str:
    """Render a summed amount, keeping a comma when the input used one."""
    if number == number.to_integral_value():
        return str(number.to_integral_value())
    text = format(number, "f").rstrip("0").rstrip(".")
    if separator == ",":
        text = text.replace(".", ",")
    return text


def _merge_quantities(quantity_entries: Sequence[str]) -> str:
    """Add amounts that share a unit and keep other text in its original order."""
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


def remember_article(user: AbstractBaseUser, name: str) -> Article | None:
    """Store the item name for later suggestions, reusing a case-insensitive match."""
    name = _normalized_name(name)
    if not name:
        return None
    existing = user.articles.filter(name__iexact=name).order_by("id").first()
    if existing is not None:
        return existing
    return user.articles.create(name=name)


def save_article(user: AbstractBaseUser, name: str, article: Article | None = None) -> Article:
    """Create an article, or rename the given one."""
    name = _normalized_name(name)
    if article is None:
        return user.articles.create(name=name)
    article.name = name
    article.save(update_fields=["name", "updated_at"])
    return article


def create_item(
    shopping_list: ShoppingList,
    *,
    name: str,
    quantity: str = "",
    checked: bool = False,
    position: int | None = None,
) -> ShoppingItem:
    """Add an item, or merge the quantity into the existing line with the same name."""
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


def _clean_list_icon(icon: str | None) -> str | None:
    """Return a known icon, None when none was given, or raise for an unknown value."""
    if icon in (None, ""):
        return None
    if icon not in ShoppingList.Icon.values:
        raise ValueError(_("Choose an icon."))
    return icon


def create_shopping_list(
    user: AbstractBaseUser,
    *,
    title: str,
    date: date,
    items: Sequence[Mapping[str, Any]] | None = None,
    position: int = 0,
    icon: str | None = None,
) -> ShoppingList:
    """Create a list and its items. An omitted icon stays the basket default."""
    icon = _clean_list_icon(icon)
    shopping_list = user.shopping_lists.create(
        title=title,
        date=date,
        position=position,
        **({"icon": icon} if icon else {}),
    )
    for item_position, item_data in enumerate(items or [], start=1):
        item_data = dict(item_data)
        create_item(shopping_list, position=item_data.pop("position", item_position), **item_data)
    return shopping_list


@transaction.atomic
def import_shopping_lists(
    user: AbstractBaseUser, lists_data: Sequence[Mapping[str, Any]]
) -> list[ShoppingList]:
    """Insert imported lists at the front and shift the user's existing lists down."""
    records = [dict(record) for record in lists_data]
    user.shopping_lists.update(position=F("position") + len(records))
    created = []
    for index, record in enumerate(records, start=1):
        record.pop("position", None)
        created.append(create_shopping_list(user, position=index, **record))
    return created


@transaction.atomic
def reorder_shopping_lists(user: AbstractBaseUser, list_ids: Sequence[int]) -> None:
    """Set list positions. The ids must be exactly this user's lists."""
    _reorder_owned(user.shopping_lists, list_ids)


@transaction.atomic
def reorder_items(shopping_list: ShoppingList, item_ids: Sequence[int]) -> None:
    """Set item positions. The ids must be exactly the items of this list."""
    existing = set(shopping_list.items.filter(id__in=item_ids).values_list("id", flat=True))
    if existing != set(item_ids) or len(item_ids) != len(existing):
        raise ValueError(_("Invalid item order."))
    for position, item_id in enumerate(item_ids, start=1):
        ShoppingItem.objects.filter(pk=item_id, shopping_list=shopping_list).update(
            position=position
        )


def _line_text(line: str | Mapping[str, Any]) -> str:
    """Read a step as a string or as a mapping with a text field."""
    if isinstance(line, str):
        return _normalized_name(line)
    return _normalized_name(line.get("text") or "")


def _write_lines(manager: Manager, lines: Sequence[str | Mapping[str, Any]] | None) -> None:
    """Replace every step with the given lines, skipping blank text."""
    manager.all().delete()
    for index, line in enumerate(lines or [], start=1):
        text = _line_text(line)
        if not text:
            continue
        position = index if isinstance(line, str) else (line.get("position") or index)
        manager.create(text=text, position=position)


def _write_ingredients(manager: Manager, ingredients: Sequence[Mapping[str, Any]] | None) -> None:
    """Replace every ingredient, skipping lines that have no name."""
    manager.all().delete()
    for index, line in enumerate(ingredients or [], start=1):
        name = _normalized_name(line.get("name") or "")
        quantity = (line.get("quantity") or "").strip()
        if not name:
            continue
        position = line.get("position") or index
        manager.create(name=name, quantity=quantity, position=position)


def _clean_image_url(image_url: str) -> str:
    """Return a stripped http(s) URL, or an empty string when none was given."""
    image_url = (image_url or "").strip()
    if not image_url:
        return ""
    try:
        URLValidator(schemes=["http", "https"])(image_url)
    except ValidationError as error:
        raise ValueError(_("Enter a valid image URL.")) from error
    return image_url


def _optional_count(value: int | str | None) -> int | None:
    """Return None for an empty value, or a non-negative whole number."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(_("Enter zero or a positive whole number."))
    try:
        amount = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(_("Enter zero or a positive whole number.")) from error
    if amount < 0:
        raise ValueError(_("Enter zero or a positive whole number."))
    return amount


def create_recipe(
    user: AbstractBaseUser,
    *,
    title: str,
    description: str = "",
    image_url: str = "",
    calories: int | None = None,
    protein: int | None = None,
    preparation_minutes: int | None = None,
    ingredients: Sequence[Mapping[str, Any]] | None = None,
    steps: Sequence[str | Mapping[str, Any]] | None = None,
    recipe: Recipe | None = None,
    position: int = 0,
) -> Recipe:
    """Create or update a recipe. Ingredients and steps are replaced only when passed."""
    title = _normalized_name(title)
    if not title:
        raise ValueError(_("Enter a title."))
    description = (description or "").strip()
    image_url = _clean_image_url(image_url)
    calories = _optional_count(calories)
    protein = _optional_count(protein)
    preparation_minutes = _optional_count(preparation_minutes)
    if recipe is None:
        recipe = user.recipes.create(
            title=title,
            description=description,
            image_url=image_url,
            calories=calories,
            protein=protein,
            preparation_minutes=preparation_minutes,
            position=position,
        )
    else:
        recipe.title = title
        recipe.description = description
        recipe.image_url = image_url
        recipe.calories = calories
        recipe.protein = protein
        recipe.preparation_minutes = preparation_minutes
        recipe.save(
            update_fields=[
                "title",
                "description",
                "image_url",
                "calories",
                "protein",
                "preparation_minutes",
                "updated_at",
            ]
        )
    if ingredients is not None:
        _write_ingredients(recipe.ingredients, ingredients)
    if steps is not None:
        _write_lines(recipe.steps, steps)
    return recipe


@transaction.atomic
def import_recipes(
    user: AbstractBaseUser, recipes_data: Sequence[Mapping[str, Any]]
) -> list[Recipe]:
    """Insert imported recipes at the front and shift the user's existing recipes down."""
    records = [dict(record) for record in recipes_data]
    user.recipes.update(position=F("position") + len(records))
    created = []
    for index, record in enumerate(records, start=1):
        record.pop("position", None)
        created.append(create_recipe(user, position=index, **record))
    return created


@transaction.atomic
def reorder_recipes(user: AbstractBaseUser, recipe_ids: Sequence[int]) -> None:
    """Set recipe positions. The ids must be exactly this user's recipes."""
    _reorder_owned(user.recipes, recipe_ids)


def add_recipe_line(
    recipe: Recipe,
    kind: Literal["ingredient", "step"],
    text: str = "",
    name: str = "",
    quantity: str = "",
) -> RecipeIngredient | RecipeStep:
    """Append an ingredient or a step at the next position."""
    manager = _recipe_lines(recipe, kind)
    position = (manager.aggregate(last=Max("position"))["last"] or 0) + 1
    if kind == "ingredient":
        return manager.create(
            name=_normalized_name(name), quantity=(quantity or "").strip(), position=position
        )
    return manager.create(text=_normalized_name(text), position=position)


def reorder_recipe_lines(
    recipe: Recipe, kind: Literal["ingredient", "step"], line_ids: Sequence[int]
) -> None:
    """Set positions for one kind of line. The ids must belong to that recipe."""
    manager = _recipe_lines(recipe, kind)
    model = manager.model
    _reorder(manager, line_ids, model, "recipe", recipe)


def _ingredient_name_and_quantity(text: str) -> tuple[str, str]:
    """Split free-text into a name and a quantity. A short token beside the amount is the unit."""
    text = _normalized_name(text)
    leading = _LEADING_INGREDIENT.match(text)
    if leading:
        amount, second, rest = (
            leading.group("amount"),
            leading.group("second"),
            leading.group("rest"),
        )
        if second and rest and len(second) <= 4:
            return _normalized_name(rest), f"{amount} {second}"
        if second and rest:
            return _normalized_name(f"{second} {rest}"), amount
        if second:
            return second, amount
        return text, ""
    trailing = _TRAILING_INGREDIENT.match(text)
    if trailing and not trailing.group("name")[:1].isdigit():
        name, amount, unit = (
            trailing.group("name"),
            trailing.group("amount"),
            trailing.group("unit"),
        )
        if unit and len(unit) <= 4:
            return _normalized_name(name), f"{amount} {unit}"
        if unit:
            return _normalized_name(f"{name} {unit}"), amount
        return _normalized_name(name), amount
    return text, ""


def add_recipe_ingredients_to_list(recipe: Recipe, shopping_list: ShoppingList) -> ShoppingList:
    """Copy the recipe's ingredients onto a list owned by the same user."""
    if shopping_list.user_id != recipe.user_id:
        raise ValueError(_("Invalid shopping list."))
    for ingredient in recipe.ingredients.all():
        create_item(shopping_list, name=ingredient.name, quantity=ingredient.quantity)
    return shopping_list


def owned_recipe(
    user: AbstractBaseUser, *, recipe_id: int | None = None, title: str = ""
) -> Recipe:
    """Return one of this user's recipes by id or unique title."""
    if recipe_id is not None:
        recipe = user.recipes.filter(pk=recipe_id).first()
        if recipe is None:
            raise ValueError(_("Recipe not found."))
        return recipe
    title = _normalized_name(title)
    if not title:
        raise ValueError(_("Choose a recipe."))
    matches = [
        recipe
        for recipe in user.recipes.all()
        if _normalized_name(recipe.title).casefold() == title.casefold()
    ]
    if not matches:
        raise ValueError(_("Recipe not found."))
    if len(matches) > 1:
        raise ValueError(_("That title matches more than one recipe."))
    return matches[0]


def owned_or_today_list(
    user: AbstractBaseUser, *, list_id: int | None = None, title: str = ""
) -> ShoppingList:
    """Return a list by id or title, or today's list, creating it when needed."""
    if list_id is not None:
        shopping_list = user.shopping_lists.filter(pk=list_id).first()
        if shopping_list is None:
            raise ValueError(_("Shopping list not found."))
        return shopping_list
    title = _normalized_name(title)
    if title:
        matches = [
            shopping_list
            for shopping_list in user.shopping_lists.all()
            if _normalized_name(shopping_list.title).casefold() == title.casefold()
        ]
        if len(matches) > 1:
            raise ValueError(_("That title matches more than one shopping list."))
        if matches:
            return matches[0]
        return create_shopping_list(user, title=title, date=timezone.localdate())
    today = timezone.localdate()
    todays = list(user.shopping_lists.filter(date=today).order_by("position", "id"))
    if len(todays) > 1:
        raise ValueError(_("There is more than one list for today. Say which list."))
    if todays:
        return todays[0]
    return create_shopping_list(user, title=_("Today"), date=today)


def set_item_checked(
    user: AbstractBaseUser,
    *,
    name: str,
    checked: bool = True,
    list_id: int | None = None,
) -> ShoppingItem:
    """Mark one of this user's items completed or open."""
    name = _normalized_name(name)
    if not name:
        raise ValueError(_("Enter an item name."))
    items = ShoppingItem.objects.filter(shopping_list__user=user)
    if list_id is not None:
        if not user.shopping_lists.filter(pk=list_id).exists():
            raise ValueError(_("Shopping list not found."))
        items = items.filter(shopping_list_id=list_id)
    matches = [
        item
        for item in items.select_related("shopping_list")
        if _normalized_name(item.name).casefold() == name.casefold()
    ]
    if not matches:
        raise ValueError(_("Item not found."))
    if list_id is None and len(matches) > 1:
        raise ValueError(_("That item is on more than one list. Say which list."))
    item = matches[0]
    item.checked = checked
    item.save(update_fields=["checked", "updated_at"])
    return item


def delete_completed_items(shopping_list: ShoppingList) -> int:
    """Remove every completed item from this list. Returns how many were deleted."""
    queryset = shopping_list.items.filter(checked=True)
    count = queryset.count()
    if count:
        queryset.delete()
    return count


def add_recipe_to_owned_list(
    user: AbstractBaseUser,
    *,
    recipe_id: int | None = None,
    recipe_title: str = "",
    list_id: int | None = None,
    list_title: str = "",
) -> ShoppingList:
    """Copy a recipe's ingredients onto a list belonging to the same user."""
    recipe = owned_recipe(user, recipe_id=recipe_id, title=recipe_title)
    shopping_list = owned_or_today_list(user, list_id=list_id, title=list_title)
    return add_recipe_ingredients_to_list(recipe, shopping_list)


def add_item_to_owned_list(
    user: AbstractBaseUser,
    *,
    name: str,
    quantity: str = "",
    list_id: int | None = None,
    list_title: str = "",
) -> ShoppingItem:
    """Add an item to a list belonging to this user."""
    name = _normalized_name(name)
    if not name:
        raise ValueError(_("Enter an item name."))
    shopping_list = owned_or_today_list(user, list_id=list_id, title=list_title)
    return create_item(shopping_list, name=name, quantity=quantity)


def _recipe_lines(recipe: Recipe, kind: Literal["ingredient", "step"]) -> Manager:
    """Return the ingredients or steps manager for this recipe."""
    if kind == "ingredient":
        return recipe.ingredients
    if kind == "step":
        return recipe.steps
    raise ValueError(_("Invalid order."))


def _reorder_owned(manager: Manager, ordered_ids: Sequence[int]) -> None:
    """Require the ids to be exactly these records, then write positions from 1."""
    existing = set(manager.filter(id__in=ordered_ids).values_list("id", flat=True))
    if (
        existing != set(ordered_ids)
        or len(ordered_ids) != len(existing)
        or manager.count() != len(ordered_ids)
    ):
        raise ValueError(_("Invalid order."))
    for position, record_id in enumerate(ordered_ids, start=1):
        manager.filter(pk=record_id).update(position=position)


def _reorder(
    manager: Manager,
    ordered_ids: Sequence[int],
    model: type[Model],
    parent_field: str,
    parent: Model,
) -> None:
    """Require the ids to be these lines, then write positions on that parent."""
    existing = set(manager.filter(id__in=ordered_ids).values_list("id", flat=True))
    if existing != set(ordered_ids) or len(ordered_ids) != len(existing):
        raise ValueError(_("Invalid order."))
    for position, line_id in enumerate(ordered_ids, start=1):
        model.objects.filter(pk=line_id, **{parent_field: parent}).update(position=position)


def shopping_list_export_data(shopping_list: ShoppingList) -> dict[str, Any]:
    """JSON for one list that Import JSON can read again."""
    return {
        "title": shopping_list.title,
        "icon": shopping_list.icon,
        "date": shopping_list.date.isoformat(),
        "items": [
            {"name": item.name, "quantity": item.quantity, "checked": item.checked}
            for item in shopping_list.items.all()
        ],
    }


def recipe_export_data(recipe: Recipe) -> dict[str, Any]:
    """JSON for one recipe that Import JSON can read again."""
    data: dict[str, Any] = {
        "title": recipe.title,
        "description": recipe.description,
        "ingredients": [
            {"name": line.name, "quantity": line.quantity} for line in recipe.ingredients.all()
        ],
        "steps": [{"text": line.text} for line in recipe.steps.all()],
    }
    if recipe.image_url:
        data["image_url"] = recipe.image_url
    if recipe.calories is not None:
        data["calories"] = recipe.calories
    if recipe.protein is not None:
        data["protein"] = recipe.protein
    if recipe.preparation_minutes is not None:
        data["preparation_minutes"] = recipe.preparation_minutes
    return data


def export_records(
    *,
    lists: Sequence[ShoppingList] | None = None,
    recipes: Sequence[Recipe] | None = None,
) -> dict[str, Any]:
    """Build an importable document from the chosen lists and recipes."""
    payload: dict[str, Any] = {}
    if lists:
        payload["lists"] = [shopping_list_export_data(shopping_list) for shopping_list in lists]
    if recipes:
        payload["recipes"] = [recipe_export_data(recipe) for recipe in recipes]
    return payload
