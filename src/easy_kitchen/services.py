import re
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Literal

from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import IntegrityError, transaction
from django.db.models import F, Manager, Max, Model
from django.utils import timezone
from django.utils.translation import gettext as _

from .departments import Department
from .models import (
    Article,
    MealPlanEntry,
    Recipe,
    RecipeIngredient,
    RecipeStep,
    ShoppingItem,
    ShoppingList,
)

_QUANTITY_AMOUNT = re.compile(r"^(\d+(?:[.,]\d+)?)\s*([^\d/–-]*)$")
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
            # Unsupported numeric expressions retain each contribution, including
            # identical fractions/ranges from repeated recipe additions.
            if not part[0].isdigit() and text_key in seen_text:
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


def remember_article(user: AbstractBaseUser, name: str, department: str | None = None) -> Article | None:
    """Store the item name for later suggestions, reusing a case-insensitive match."""
    if department is not None and department not in {"", *Department.values}:
        raise ValueError(_("Invalid department."))
    name = _normalized_name(name)
    if not name:
        return None
    existing = user.articles.filter(name__iexact=name).order_by("id").first()
    if existing is not None:
        if department is not None and existing.department != department:
            existing.department = department
            existing.save(update_fields=["department", "updated_at"])
        return existing
    try:
        with transaction.atomic():
            return user.articles.create(name=name, department=department or "")
    except IntegrityError:
        existing = user.articles.filter(name__iexact=name).order_by("id").first()
        if existing is None:
            raise
        return remember_article(user, name, department)


def save_article(user: AbstractBaseUser, name: str, article: Article | None = None,
                 department: str | None = None) -> Article:
    """Create an article, or rename the given one."""
    name = _normalized_name(name)
    if article is None:
        return user.articles.create(name=name, department=department or "")
    article.name = name
    if department is not None:
        article.department = department
    article.save(update_fields=["name", "department", "updated_at"])
    return article


class QuantityOverflowError(ValueError):
    """The accumulated quantity cannot fit in the shopping item's storage field."""


@transaction.atomic
def create_item(
    shopping_list: ShoppingList,
    *,
    name: str,
    quantity: str = "",
    checked: bool = False,
    position: int | None = None,
    department: str | None = None,
) -> ShoppingItem:
    """Add an item, or merge the quantity into the existing line with the same name."""
    name = _normalized_name(name)
    quantity = (quantity or "").strip()
    # Lock a row that exists even before the first item is added. All additions
    # to this list then observe the preceding committed quantity and article.
    ShoppingList.objects.select_for_update().get(pk=shopping_list.pk)
    article = remember_article(shopping_list.user, name, department)
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
        merged = _merge_quantities(quantity_entries)
        _validate_item_quantity(merged)
        existing.quantity = merged
        existing.checked = False
        if department is not None:
            existing.department = department
        existing.save(update_fields=["quantity", "checked", "department", "updated_at"])
        return existing
    if position is None:
        position = (shopping_list.items.aggregate(last=Max("position"))["last"] or 0) + 1
    _validate_item_quantity(quantity)
    return ShoppingItem.objects.create(
        shopping_list=shopping_list,
        name=name,
        quantity=quantity,
        department=article.department if article else "",
        checked=checked,
        position=position,
    )


def _validate_item_quantity(quantity: str) -> None:
    limit = ShoppingItem._meta.get_field("quantity").max_length
    if len(quantity) > limit:
        raise QuantityOverflowError(
            _("The combined quantity exceeds %(limit)d characters. Use a shorter quantity.")
            % {"limit": limit}
        )


def _clean_list_icon(icon: str | None) -> str | None:
    """Return a known icon, None when none was given, or raise for an unknown value."""
    if icon in (None, ""):
        return None
    if icon not in ShoppingList.Icon.values:
        raise ValueError(_("Choose an icon."))
    return icon


@transaction.atomic
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
    if (existing != set(item_ids) or len(item_ids) != len(existing)
            or shopping_list.items.count() != len(item_ids)):
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


@transaction.atomic
def create_recipe(
    user: AbstractBaseUser,
    *,
    title: str,
    description: str = "",
    image_url: str = "",
    calories: int | None = None,
    protein: int | None = None,
    carbohydrates: int | None = None,
    fat: int | None = None,
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
    carbohydrates = _optional_count(carbohydrates)
    fat = _optional_count(fat)
    preparation_minutes = _optional_count(preparation_minutes)
    if recipe is None:
        recipe = user.recipes.create(
            title=title,
            description=description,
            image_url=image_url,
            calories=calories,
            protein=protein,
            carbohydrates=carbohydrates,
            fat=fat,
            preparation_minutes=preparation_minutes,
            position=position,
        )
    else:
        recipe.title = title
        recipe.description = description
        recipe.image_url = image_url
        recipe.calories = calories
        recipe.protein = protein
        recipe.carbohydrates = carbohydrates
        recipe.fat = fat
        recipe.preparation_minutes = preparation_minutes
        recipe.save(
            update_fields=[
                "title",
                "description",
                "image_url",
                "calories",
                "protein",
                "carbohydrates",
                "fat",
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


@transaction.atomic
def add_recipe_ingredients_to_list(recipe: Recipe, shopping_list: ShoppingList) -> ShoppingList:
    """Copy the recipe's ingredients onto a list owned by the same user."""
    if shopping_list.user_id != recipe.user_id:
        raise ValueError(_("Invalid shopping list."))
    for ingredient in recipe.ingredients.all():
        create_item(shopping_list, name=ingredient.name, quantity=ingredient.quantity)
    return shopping_list


@transaction.atomic
def copy_recipe_to_list(
    recipe: Recipe, *, shopping_list: ShoppingList | None = None, title: str = ""
) -> ShoppingList:
    """Create the web UI's new target and copy ingredients as one operation."""
    if title:
        shopping_list = create_shopping_list(recipe.user, title=title, date=timezone.localdate())
    if shopping_list is None:
        raise ValueError(_("Invalid shopping list."))
    return add_recipe_ingredients_to_list(recipe, shopping_list)


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


@transaction.atomic
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
    department: str | None = None,
) -> ShoppingItem:
    """Add an item to a list belonging to this user."""
    name = _normalized_name(name)
    if not name:
        raise ValueError(_("Enter an item name."))
    shopping_list = owned_or_today_list(user, list_id=list_id, title=list_title)
    return create_item(shopping_list, name=name, quantity=quantity, department=department)


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
    if (existing != set(ordered_ids) or len(ordered_ids) != len(existing)
            or manager.count() != len(ordered_ids)):
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
            {"name": item.name, "quantity": item.quantity, "checked": item.checked, "department": item.department}
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
    if recipe.carbohydrates is not None:
        data["carbohydrates"] = recipe.carbohydrates
    if recipe.fat is not None:
        data["fat"] = recipe.fat
    if recipe.preparation_minutes is not None:
        data["preparation_minutes"] = recipe.preparation_minutes
    return data


def recipe_search_documents(user: AbstractBaseUser) -> dict[str, dict[str, str]]:
    """Provide the user's recipe titles and pictures for planner autocomplete."""
    return {
        str(recipe.pk): {"text": recipe.title, "picture_url": recipe.picture_url}
        for recipe in user.recipes.all()
    }



def week_start_for(day: date) -> date:
    """Return the Monday on or before the given day."""
    return day - timedelta(days=day.weekday())


def week_dates(week_start: date) -> list[date]:
    """Return Monday through Sunday for a week that starts on Monday."""
    return [week_start + timedelta(days=offset) for offset in range(7)]


def meal_plan_for_week(user: AbstractBaseUser, week_start: date) -> dict[date, MealPlanEntry | None]:
    """Map each day in the week to a plan entry, if one exists."""
    dates = week_dates(week_start)
    entries = {
        entry.date: entry
        for entry in MealPlanEntry.objects.filter(user=user, date__in=dates).select_related(
            "recipe"
        )
    }
    return {day: entries.get(day) for day in dates}


def set_meal_plan_recipe(user: AbstractBaseUser, day: date, recipe: Recipe) -> MealPlanEntry:
    """Assign one recipe to a day for this user."""
    if recipe.user_id != user.pk:
        raise ValueError(_("Recipe not found."))
    entry, _created = MealPlanEntry.objects.update_or_create(
        user=user,
        date=day,
        defaults={"recipe": recipe},
    )
    return entry


def clear_meal_plan_day(user: AbstractBaseUser, day: date) -> None:
    """Remove the planned recipe for one day."""
    MealPlanEntry.objects.filter(user=user, date=day).delete()


def planned_recipe_count(user: AbstractBaseUser, week_start: date) -> int:
    """Return how many days in the week have a planned recipe."""
    plan = meal_plan_for_week(user, week_start)
    return sum(1 for day in week_dates(week_start) if plan.get(day) and plan[day].recipe_id)


@transaction.atomic
def add_meal_plan_week_to_list(
    user: AbstractBaseUser,
    week_start: date,
    *,
    shopping_list: ShoppingList | None,
    title: str = "",
) -> ShoppingList:
    """Copy planned recipes for the week onto one shopping list, merging quantities."""
    dates = week_dates(week_start)
    entries = {
        entry.date: entry
        for entry in MealPlanEntry.objects.filter(
            user=user, date__in=dates, recipe__isnull=False
        ).select_related("recipe")
    }
    planned = [entries[day].recipe for day in dates if day in entries and entries[day].recipe]
    if not planned:
        raise ValueError(_("This week has no planned recipes yet."))

    if title:
        target = create_shopping_list(user, title=title, date=timezone.localdate())
    elif shopping_list is not None:
        if shopping_list.user_id != user.pk:
            raise ValueError(_("Invalid shopping list."))
        target = shopping_list
    else:
        raise ValueError(_("Choose a list or enter a title for a new one."))

    for recipe in planned:
        add_recipe_ingredients_to_list(recipe, target)
    return target


def meal_plan_day_data(day: date, recipe: Recipe | None = None) -> dict[str, Any]:
    """Represent a calendar day consistently in the API and MCP."""
    return {
        "date": day.isoformat(),
        "recipe": {"id": recipe.pk, "title": recipe.title} if recipe else None,
    }


def _complete_meal_plan_week(day: date) -> date:
    """Normalize a date to Monday and reject a week beyond the calendar range."""
    start = week_start_for(day)
    try:
        week_dates(start)
    except OverflowError:
        raise ValueError(_("Choose a complete calendar week.")) from None
    return start


def meal_plan_week_data(user: AbstractBaseUser, week: date | None = None) -> dict[str, Any]:
    """Read all seven days of the selected local week for the current user."""
    start = _complete_meal_plan_week(week if week is not None else timezone.localdate())
    plan = meal_plan_for_week(user, start)
    return {
        "week_start": start.isoformat(),
        "week_end": week_dates(start)[-1].isoformat(),
        "days": [
            meal_plan_day_data(day, entry.recipe if entry else None)
            for day, entry in plan.items()
        ],
    }


def plan_owned_recipe(
    user: AbstractBaseUser,
    day: date,
    *,
    recipe_id: int | None = None,
    recipe_title: str = "",
) -> dict[str, Any]:
    """Assign or replace a day using an owned recipe id or an unambiguous title."""
    recipe = owned_recipe(user, recipe_id=recipe_id, title=recipe_title)
    set_meal_plan_recipe(user, day, recipe)
    return meal_plan_day_data(day, recipe)


def add_meal_plan_to_owned_list(
    user: AbstractBaseUser,
    week: date,
    *,
    list_id: int | None = None,
    title: str = "",
) -> ShoppingList:
    """Copy a complete week to exactly one owned list or a newly named list."""
    start = _complete_meal_plan_week(week)
    title = _normalized_name(title)
    if (list_id is not None) == bool(title):
        raise ValueError(_("Choose exactly one shopping list or a title for a new one."))
    target = None
    if list_id is not None:
        target = user.shopping_lists.filter(pk=list_id).first()
        if target is None:
            raise ValueError(_("Shopping list not found."))
    return add_meal_plan_week_to_list(user, start, shopping_list=target, title=title)


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
