import re
import unicodedata
from difflib import SequenceMatcher
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import uuid4

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Exists, F, Manager, Max, Model, OuterRef, Q
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext as _, override

from .departments import DEFAULT_DEPARTMENTS
from .errors import ObjectNotFoundError, QuantityOverflowError, SelectionMismatchError, ServiceError
from .validation import (
    NAME_LIMIT, QUANTITY_LIMIT, RECIPE_FIELDS, COUNT_LIMIT, DEFAULT_LIST_LIMIT, MAX_LIST_LIMIT,
    clean_recipe_changes, clean_text,
)
from .models import (
    Article,
    Department,
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


def seed_default_departments(user: AbstractBaseUser, *, using: str = "default") -> None:
    """Create the starter catalogue once when a new account is created."""
    Department.objects.using(using).bulk_create([
        Department(user_id=user.pk, code=code, name=name, position=position)
        for position, (code, name) in enumerate(DEFAULT_DEPARTMENTS, start=1)
    ])


class DepartmentResolutionError(ServiceError):
    """A department needs an explicit choice; approximate matches never authorize a write."""

    def __init__(self, query: str, *, ambiguous: bool = False, candidates: list[dict] | None = None):
        self.query = query
        self.code = "department_ambiguous" if ambiguous else "department_not_found"
        self.candidates = candidates or []
        message = (_("Invalid department. More than one department matches; choose a saved code.")
                   if ambiguous else _("Invalid department. No exact match was found; choose a saved code."))
        super().__init__(str(message))

    def as_dict(self) -> dict:
        return {"code": self.code, "query": self.query, "message": str(self), "candidates": self.candidates}


def department_data(department: Department) -> dict:
    """Public department metadata; ownership is established before calling this function."""
    return {"id": department.pk, "code": department.code, "name": department.name, "label": str(department)}


def _owned_record(queryset, pk: int, message):
    record = queryset.filter(pk=pk).first()
    if record is None:
        raise ObjectNotFoundError(message)
    return record


def get_owned_recipe(user: AbstractBaseUser, *, recipe_id: int) -> Recipe:
    return _owned_record(user.recipes.prefetch_related("ingredients", "steps"), recipe_id, _("Recipe not found."))


def get_owned_shopping_list(user: AbstractBaseUser, *, list_id: int) -> ShoppingList:
    return _owned_record(user.shopping_lists.prefetch_related("items__department"), list_id, _("Shopping list not found."))


def get_owned_shopping_item(user: AbstractBaseUser, *, item_id: int) -> ShoppingItem:
    return _owned_record(ShoppingItem.objects.filter(shopping_list__user=user).select_related("department"), item_id, _("Item not found."))


def get_owned_article(user: AbstractBaseUser, *, article_id: int) -> Article:
    return _owned_record(user.articles.select_related("department"), article_id, _("Article not found."))


def get_owned_department(user: AbstractBaseUser, *, department_id: int) -> Department:
    return _owned_record(user.departments.all(), department_id, _("Department not found."))


def delete_owned_recipe(user: AbstractBaseUser, *, recipe_id: int) -> None:
    """Delete the owned recipe with its children and existing planner references."""
    count, _details = user.recipes.filter(pk=recipe_id).delete()
    if not count:
        raise ObjectNotFoundError(_("Recipe not found."))


def delete_owned_shopping_list(user: AbstractBaseUser, *, list_id: int) -> None:
    """Delete the owned list and entries, retaining saved articles and recipes."""
    count, _details = user.shopping_lists.filter(pk=list_id).delete()
    if not count:
        raise ObjectNotFoundError(_("Shopping list not found."))


def _collection_window(q, limit, offset):
    q = clean_text(q, field="q", limit=NAME_LIMIT, normalize=True)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIST_LIMIT:
        raise ServiceError(_("Choose a limit between 1 and %(maximum)d.") % {"maximum": MAX_LIST_LIMIT}, field="limit")
    if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= COUNT_LIMIT:
        raise ServiceError(_("Choose an offset between 0 and %(maximum)d.") % {"maximum": COUNT_LIMIT}, field="offset")
    return q, slice(offset, offset + limit)


def query_owned_recipes(user, *, q="", is_favorite=None, limit=DEFAULT_LIST_LIMIT, offset=0, summary=False):
    q, window = _collection_window(q, limit, offset)
    recipes = user.recipes.all()
    if is_favorite is not None:
        recipes = recipes.filter(is_favorite=is_favorite)
    for term in q.split():
        ingredients = RecipeIngredient.objects.filter(recipe_id=OuterRef("pk"), name__icontains=term)
        recipes = recipes.filter(Q(title__icontains=term) | Q(description__icontains=term) | Q(Exists(ingredients)))
    if not summary:
        recipes = recipes.prefetch_related("ingredients", "steps")
    return recipes[window]


def query_owned_shopping_lists(user, *, q="", date_from=None, date_to=None, limit=DEFAULT_LIST_LIMIT, offset=0, summary=False):
    q, window = _collection_window(q, limit, offset)
    if date_from is not None and date_to is not None and date_from > date_to:
        raise ServiceError(_("Start date must not be after end date."), field="date_from")
    lists = user.shopping_lists.all()
    for term in q.split():
        lists = lists.filter(title__icontains=term)
    if date_from is not None:
        lists = lists.filter(date__gte=date_from)
    if date_to is not None:
        lists = lists.filter(date__lte=date_to)
    if not summary:
        lists = lists.prefetch_related("items__department")
    return lists[window]


def query_owned_shopping_items(user, *, q="", checked=None, list_id=None, limit=DEFAULT_LIST_LIMIT, offset=0):
    q, window = _collection_window(q, limit, offset)
    items = ShoppingItem.objects.filter(shopping_list__user=user).select_related("department")
    if list_id is not None:
        if not user.shopping_lists.filter(pk=list_id).exists():
            raise ObjectNotFoundError(_("Shopping list not found."))
        items = items.filter(shopping_list_id=list_id)
    if checked is not None:
        items = items.filter(checked=checked)
    for term in q.split():
        items = items.filter(name__icontains=term)
    return items[window]


def query_owned_articles(user, *, q="", department=None, limit=DEFAULT_LIST_LIMIT, offset=0):
    q, window = _collection_window(q, limit, offset)
    articles = user.articles.select_related("department")
    if department is not None:
        articles = articles.filter(department=resolve_department(user, department))
    for term in q.split():
        articles = articles.filter(name__icontains=term)
    return articles[window]


def list_department_data(user: AbstractBaseUser, *, q="", limit=DEFAULT_LIST_LIMIT, offset=0) -> list[dict]:
    """List only this user's departments, sorted by the displayed label."""
    q, window = _collection_window(q, limit, offset)

    def sort_key(department):
        label = unicodedata.normalize("NFKD", str(department).casefold())
        return "".join(character for character in label if not unicodedata.combining(character))

    records = [department_data(department) for department in sorted(user.departments.all(), key=sort_key)]
    terms = _department_match_key(q).split()
    if terms:
        records = [record for record in records if all(term in _department_match_key(
            " ".join((record["code"], record["name"], record["label"]))) for term in terms)]
    return records[window]


def _department_match_key(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold()
    text = text.translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue"}))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = re.sub(r"[&+/]", " and ", text)
    words = re.findall(r"[^\W_]+", text)
    return " ".join("and" if word == "und" else word for word in words)


def resolve_department(user: AbstractBaseUser, value: Department | str | None) -> Department | None:
    """Resolve owned codes or unambiguous names; return suggestions instead of guessing."""
    if value is None or value == "":
        return None
    if isinstance(value, Department):
        if value.user_id != user.pk:
            raise DepartmentResolutionError(value.code)
        try:
            return user.departments.get(pk=value.pk)
        except Department.DoesNotExist:
            raise DepartmentResolutionError(value.code) from None
    query = value.strip()
    if not query:
        return None
    exact = user.departments.filter(code=query).first()
    if exact is not None:
        return exact
    departments = list(user.departments.all())
    names = {department.pk: {department.code, department.name} for department in departments}
    for language, label in settings.LANGUAGES:
        with override(language):
            for department in departments:
                names[department.pk].add(str(department))
    keys = {pk: {_department_match_key(name) for name in variants} for pk, variants in names.items()}
    query_key = _department_match_key(query)
    matches = [department for department in departments if query_key and query_key in keys[department.pk]]

    def candidate(department):
        return {key: value for key, value in department_data(department).items() if key != "id"}

    if len(matches) == 1:
        return matches[0]
    if matches:
        raise DepartmentResolutionError(query, ambiguous=True, candidates=[candidate(department) for department in matches])
    ranked = []
    query_words = [word for word in query_key.split() if word != "and"]
    for department in departments:
        score = 0.0
        for key in keys[department.pk]:
            score = max(score, SequenceMatcher(None, query_key, key, autojunk=False).ratio())
            if query_words and all(len(word) >= 3 and any(part.startswith(word) for part in key.split()) for word in query_words):
                score = max(score, 0.65)
        if query_key and score >= 0.45:
            ranked.append((score, department))
    ranked.sort(key=lambda entry: (-entry[0], str(entry[1]).casefold(), entry[1].code))
    raise DepartmentResolutionError(query, candidates=[candidate(department) for score, department in ranked[:5]])


def remember_article(user: AbstractBaseUser, name: str, department: Department | str | None = None) -> Article | None:
    """Store the item name for later suggestions, reusing a case-insensitive match."""
    resolved_department = resolve_department(user, department)
    name = _normalized_name(name)
    if not name:
        return None
    existing = user.articles.filter(name__iexact=name).order_by("id").first()
    if existing is not None:
        if department is not None and existing.department_id != (resolved_department.pk if resolved_department else None):
            existing.department = resolved_department
            existing.save(update_fields=["department", "updated_at"])
        return existing
    try:
        with transaction.atomic():
            return user.articles.create(name=name, department=resolved_department)
    except IntegrityError:
        existing = user.articles.filter(name__iexact=name).order_by("id").first()
        if existing is None:
            raise
        return remember_article(user, name, department)


def save_article(user: AbstractBaseUser, name: str, article: Article | None = None,
                 department: Department | str | None = None) -> Article:
    """Create an article, or rename the given one."""
    name = _normalized_name(name)
    if article is None:
        return user.articles.create(name=name, department=resolve_department(user, department))
    article.name = name
    if department is not None:
        article.department = resolve_department(user, department)
    article.save(update_fields=["name", "department", "updated_at"])
    return article


@transaction.atomic
def save_articles(user: AbstractBaseUser, records: Sequence[Mapping[str, Any]], deleted_ids: Sequence[int]) -> None:
    """Save an article draft atomically, permitting name swaps and name reuse after deletion."""
    existing = {article.pk: article for article in user.articles.select_for_update()}
    ids = [record["id"] for record in records if record["id"] is not None]
    all_ids = [*ids, *deleted_ids]
    if len(all_ids) != len(set(all_ids)) or not set(all_ids) <= existing.keys():
        raise ServiceError(_("Invalid article selection."))
    names = {article.name.casefold() for pk, article in existing.items() if pk not in all_ids}
    for record in records:
        name = _normalized_name(record["name"])
        if not name:
            raise ServiceError(_("Enter an article name."))
        if name.casefold() in names:
            raise ServiceError(_("An article with this name already exists."))
        resolve_department(user, record["department"])
        names.add(name.casefold())
    user.articles.filter(pk__in=deleted_ids).delete()
    changed = [record for record in records if record["id"] is None or
               (existing[record["id"]].name, existing[record["id"]].department) !=
               (record["name"], record["department"])]
    # Free names before applying renames so two existing articles can exchange names.
    for record in changed:
        if record["id"] is not None:
            user.articles.filter(pk=record["id"]).update(name=f"__article_draft_{uuid4().hex}")
    for record in changed:
        save_article(user, record["name"], article=existing.get(record["id"]), department=record["department"] or "")


@transaction.atomic
def save_departments(user: AbstractBaseUser, records: Sequence[Mapping[str, Any]], deleted_ids: Sequence[int]) -> None:
    """Save only this user's department draft, keeping existing codes and references stable."""
    existing = {department.pk: department for department in user.departments.select_for_update()}
    ids = [record["id"] for record in records if record["id"] is not None]
    all_ids = [*ids, *deleted_ids]
    if len(all_ids) != len(set(all_ids)) or not set(all_ids) <= existing.keys():
        raise ServiceError(_("Invalid department selection."))
    names = {department.name.casefold() for pk, department in existing.items() if pk not in all_ids}
    for record in records:
        name = _normalized_name(record["name"])
        if not name or len(name) > 100:
            raise ServiceError(_("Enter a department name."))
        if name.casefold() in names:
            raise ServiceError(_("A department with this name already exists."))
        names.add(name.casefold())
    user.departments.filter(pk__in=deleted_ids).delete()
    codes = {department.code for pk, department in existing.items() if pk not in deleted_ids}
    position = max((department.position for department in existing.values()), default=0)
    for record in records:
        name = _normalized_name(record["name"])
        if record["id"] is not None:
            department = existing[record["id"]]
            if department.name != name:
                department.name = name
                department.save(update_fields=["name"])
        else:
            base = slugify(name)[:20] or "department"
            code, suffix = base, 2
            while code in codes:
                tail = f"-{suffix}"
                code = base[:20-len(tail)] + tail
                suffix += 1
            codes.add(code)
            position += 1
            user.departments.create(code=code, name=name, position=position)


def _checked_changes(changes: Mapping[str, Any], allowed: set[str]) -> dict[str, Any]:
    if set(changes) - allowed:
        raise ServiceError(_("Unsupported update field."))
    return dict(changes)


def _validate_update(instance: Model) -> None:
    try:
        instance.full_clean()
    except ValidationError as error:
        raise ServiceError(" ".join(error.messages)) from None


@transaction.atomic
def update_owned_shopping_item(user: AbstractBaseUser, *, item_id: int, changes: Mapping[str, Any]) -> ShoppingItem:
    """Replace supplied item fields without merging quantities or resetting checked state."""
    item = ShoppingItem.objects.select_for_update().filter(pk=item_id, shopping_list__user=user).first()
    if item is None:
        raise ObjectNotFoundError(_("Item not found."))
    values = _checked_changes(changes, {"name", "quantity", "department", "checked"})
    previous = (item.name, item.department_id)
    for field, value in values.items():
        if field == "department":
            value = resolve_department(user, value)
        if field == "name":
            value = _normalized_name(value)
        setattr(item, field, value)
    _validate_update(item)
    if values:
        item.save(update_fields=[*values, "updated_at"])
        changed = previous != (item.name, item.department_id)
        if {"name", "quantity", "department"} & values.keys():
            remember_article(user, item.name, (item.department or "") if changed else None)
    return item


@transaction.atomic
def update_owned_shopping_list(user: AbstractBaseUser, *, list_id: int, changes: Mapping[str, Any]) -> ShoppingList:
    """Update list metadata; replace items only when explicitly supplied."""
    shopping_list = user.shopping_lists.select_for_update().filter(pk=list_id).first()
    if shopping_list is None:
        raise ObjectNotFoundError(_("Shopping list not found."))
    values = _checked_changes(changes, {"title", "date", "icon", "items"})
    items = values.pop("items", None)
    for field, value in values.items():
        if field == "title":
            value = _normalized_name(value)
        setattr(shopping_list, field, value)
    _validate_update(shopping_list)
    if values:
        shopping_list.save(update_fields=[*values, "updated_at"])
    if items is not None:
        shopping_list.items.all().delete()
        for position, record in enumerate(items, start=1):
            record = dict(record)
            create_item(shopping_list, position=record.pop("position", position), **record)
    return shopping_list


@transaction.atomic
def update_owned_article(user: AbstractBaseUser, *, article_id: int, changes: Mapping[str, Any]) -> Article:
    """Change an article default without rewriting existing shopping-list entries."""
    article = user.articles.select_for_update().filter(pk=article_id).first()
    if article is None:
        raise ObjectNotFoundError(_("Article not found."))
    values = _checked_changes(changes, {"name", "department"})
    name = _normalized_name(values.get("name", article.name))
    department = resolve_department(user, values["department"]) if "department" in values else article.department
    article.name, article.department = name, department
    _validate_update(article)
    if values:
        save_articles(user, [{"id": article.pk, "name": name, "department": department.code if department else ""}], [])
    return article


@transaction.atomic
def update_owned_department(user: AbstractBaseUser, *, department_id: int, changes: Mapping[str, Any]) -> Department:
    """Rename an owned department, preserving its stable code and all references."""
    department = user.departments.select_for_update().filter(pk=department_id).first()
    if department is None:
        raise ObjectNotFoundError(_("Department not found."))
    values = _checked_changes(changes, {"name"})
    if values:
        save_departments(user, [{"id": department.pk, "name": values["name"]}], [])
        department.refresh_from_db()
    return department


def set_owned_recipe_favorite(
    user: AbstractBaseUser, *, is_favorite: bool, recipe_id: int | None = None, recipe_title: str = "",
) -> Recipe:
    """Set an explicit favorite state, making retries safe."""
    if not isinstance(is_favorite, bool):
        raise ServiceError(_("Invalid request."))
    recipe = owned_recipe(user, recipe_id=recipe_id, title=recipe_title)
    recipe.is_favorite = is_favorite
    recipe.save(update_fields=["is_favorite", "updated_at"])
    return recipe


@transaction.atomic
def create_item(
    shopping_list: ShoppingList,
    *,
    name: str,
    quantity: str = "",
    checked: bool = False,
    position: int | None = None,
    department: Department | str | None = None,
) -> ShoppingItem:
    """Add an item, or merge the quantity into the existing line with the same name."""
    name = clean_text(name, field="name", limit=NAME_LIMIT, required=True, normalize=True)
    quantity = clean_text(quantity, field="quantity", limit=QUANTITY_LIMIT)
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
            existing.department = resolve_department(shopping_list.user, department)
        existing.save(update_fields=["quantity", "checked", "department", "updated_at"])
        return existing
    if position is None:
        position = (shopping_list.items.aggregate(last=Max("position"))["last"] or 0) + 1
    _validate_item_quantity(quantity)
    return ShoppingItem.objects.create(
        shopping_list=shopping_list,
        name=name,
        quantity=quantity,
        department=article.department if article else None,
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
        raise ServiceError(_("Choose an icon."))
    return icon


@transaction.atomic
def create_shopping_list(
    user: AbstractBaseUser,
    *,
    title: str,
    date: date | None = None,
    items: Sequence[Mapping[str, Any]] | None = None,
    position: int = 0,
    icon: str | None = None,
) -> ShoppingList:
    """Create a list and its items. An omitted icon stays the basket default."""
    title = clean_text(title, field="title", limit=NAME_LIMIT, required=True, normalize=True)
    icon = _clean_list_icon(icon)
    shopping_list = user.shopping_lists.create(
        title=title,
        date=date or timezone.localdate(),
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
    ShoppingList.objects.select_for_update().get(pk=shopping_list.pk)
    _reorder_owned(shopping_list.items, item_ids)


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
    changes = clean_recipe_changes({
        "title": title, "description": description, "image_url": image_url,
        "calories": calories, "protein": protein, "carbohydrates": carbohydrates,
        "fat": fat, "preparation_minutes": preparation_minutes,
        **({"ingredients": list(ingredients)} if ingredients is not None else {}),
        **({"steps": list(steps)} if steps is not None else {}),
    })
    if recipe is None:
        values = {field: changes[field] for field in RECIPE_FIELDS}
        recipe = user.recipes.create(position=position, **values)
        # Scalars are already saved; only write supplied children below.
        changes = {key: value for key, value in changes.items() if key not in RECIPE_FIELDS}
    else:
        recipe = user.recipes.select_for_update().filter(pk=recipe.pk).first()
        if recipe is None:
            raise ObjectNotFoundError(_("Recipe not found."))
    return _save_recipe_changes(recipe, changes)


def _save_recipe_changes(recipe: Recipe, changes: Mapping[str, Any]) -> Recipe:
    """Write only supplied scalars and replace only supplied child collections."""
    fields = [field for field in RECIPE_FIELDS if field in changes]
    for field in fields:
        setattr(recipe, field, changes[field])
    if changes:
        recipe.save(update_fields=[*fields, "updated_at"])
    if "ingredients" in changes:
        _write_ingredients(recipe.ingredients, changes["ingredients"])
    if "steps" in changes:
        _write_lines(recipe.steps, changes["steps"])
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


@transaction.atomic
def reorder_recipe_lines(
    recipe: Recipe, kind: Literal["ingredient", "step"], line_ids: Sequence[int]
) -> None:
    """Set positions for one kind of line. The ids must belong to that recipe."""
    Recipe.objects.select_for_update().get(pk=recipe.pk)
    manager = _recipe_lines(recipe, kind)
    _reorder_owned(manager, line_ids)


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
        raise ServiceError(_("Invalid shopping list."))
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
        raise ServiceError(_("Invalid shopping list."))
    return add_recipe_ingredients_to_list(recipe, shopping_list)


def owned_recipe(
    user: AbstractBaseUser, *, recipe_id: int | None = None, title: str = ""
) -> Recipe:
    """Return one of this user's recipes by id or unique title."""
    if recipe_id is not None:
        recipe = user.recipes.filter(pk=recipe_id).first()
        if recipe is None:
            raise ObjectNotFoundError(_("Recipe not found."))
        if title.strip() and _normalized_name(title).casefold() != _normalized_name(recipe.title).casefold():
            raise SelectionMismatchError(_("The supplied ID and title do not match."), field="recipe_title")
        return recipe
    title = _normalized_name(title)
    if not title:
        raise ServiceError(_("Choose a recipe."))
    matches = [
        recipe
        for recipe in user.recipes.all()
        if _normalized_name(recipe.title).casefold() == title.casefold()
    ]
    if not matches:
        raise ObjectNotFoundError(_("Recipe not found."))
    if len(matches) > 1:
        raise ServiceError(_("That title matches more than one recipe."))
    return matches[0]


@transaction.atomic
def update_owned_recipe(
    user: AbstractBaseUser,
    *,
    changes: Mapping[str, Any],
    recipe_id: int | None = None,
    recipe_title: str = "",
) -> Recipe:
    """Update only supplied fields of an owned recipe using the shared writer."""
    recipe = owned_recipe(user, recipe_id=recipe_id, title=recipe_title)
    recipe = user.recipes.select_for_update().get(pk=recipe.pk)
    return _save_recipe_changes(recipe, clean_recipe_changes(changes))


def owned_or_today_list(
    user: AbstractBaseUser, *, list_id: int | None = None, title: str = ""
) -> ShoppingList:
    """Return a list by id or title, or today's list, creating it when needed."""
    if list_id is not None:
        shopping_list = user.shopping_lists.filter(pk=list_id).first()
        if shopping_list is None:
            raise ObjectNotFoundError(_("Shopping list not found."))
        if title.strip() and _normalized_name(title).casefold() != _normalized_name(shopping_list.title).casefold():
            raise SelectionMismatchError(_("The supplied ID and title do not match."), field="list_title")
        return shopping_list
    title = _normalized_name(title)
    if title:
        matches = [
            shopping_list
            for shopping_list in user.shopping_lists.all()
            if _normalized_name(shopping_list.title).casefold() == title.casefold()
        ]
        if len(matches) > 1:
            raise ServiceError(_("That title matches more than one shopping list."))
        if matches:
            return matches[0]
        return create_shopping_list(user, title=title, date=timezone.localdate())
    today = timezone.localdate()
    todays = list(user.shopping_lists.filter(date=today).order_by("position", "id"))
    if len(todays) > 1:
        raise ServiceError(_("There is more than one list for today. Say which list."))
    if todays:
        return todays[0]
    return create_shopping_list(user, title=_("Today"), date=today)


def set_item_checked(
    user: AbstractBaseUser,
    *,
    name: str = "",
    checked: bool = True,
    list_id: int | None = None,
    item_id: int | None = None,
) -> ShoppingItem:
    """Mark one of this user's items completed or open."""
    if not isinstance(checked, bool):
        raise ServiceError(_("Invalid request."))
    if item_id is not None:
        item = ShoppingItem.objects.filter(pk=item_id, shopping_list__user=user)
        if list_id is not None:
            item = item.filter(shopping_list_id=list_id)
        item = item.first()
        if item is None:
            raise ObjectNotFoundError(_("Item not found."))
        if name.strip() and _normalized_name(name).casefold() != _normalized_name(item.name).casefold():
            raise SelectionMismatchError(_("The supplied ID and name do not match."), field="name")
        return update_owned_shopping_item(user, item_id=item.pk, changes={"checked": checked})
    name = _normalized_name(name)
    if not name:
        raise ServiceError(_("Enter an item name."))
    items = ShoppingItem.objects.filter(shopping_list__user=user)
    if list_id is not None:
        if not user.shopping_lists.filter(pk=list_id).exists():
            raise ObjectNotFoundError(_("Shopping list not found."))
        items = items.filter(shopping_list_id=list_id)
    matches = [
        item
        for item in items.select_related("shopping_list")
        if _normalized_name(item.name).casefold() == name.casefold()
    ]
    if not matches:
        raise ObjectNotFoundError(_("Item not found."))
    if len(matches) > 1:
        message = (_("That item is on more than one list. Say which list.") if list_id is None
                   else _("That name matches more than one item. Choose an item ID."))
        raise ServiceError(message)
    item = matches[0]
    return update_owned_shopping_item(user, item_id=item.pk, changes={"checked": checked})


def delete_completed_items(shopping_list: ShoppingList) -> int:
    """Remove every completed item from this list. Returns how many were deleted."""
    count, _details = shopping_list.items.filter(checked=True).delete()
    return count


def delete_owned_shopping_item(user: AbstractBaseUser, *, item_id: int) -> None:
    """Delete only the owned list entry, retaining the saved article and list."""
    count, _details = ShoppingItem.objects.filter(pk=item_id, shopping_list__user=user).delete()
    if not count:
        raise ObjectNotFoundError(_("Item not found."))


def delete_completed_items_from_owned_list(user: AbstractBaseUser, *, list_id: int) -> int:
    """Delete completed entries from an existing owned list, never creating one."""
    shopping_list = user.shopping_lists.filter(pk=list_id).first()
    if shopping_list is None:
        raise ObjectNotFoundError(_("Shopping list not found."))
    return delete_completed_items(shopping_list)


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


@transaction.atomic
def add_item_to_owned_list(
    user: AbstractBaseUser,
    *,
    name: str,
    quantity: str = "",
    list_id: int | None = None,
    list_title: str = "",
    department: Department | str | None = None,
) -> ShoppingItem:
    """Add an item to a list belonging to this user."""
    name = _normalized_name(name)
    if not name:
        raise ServiceError(_("Enter an item name."))
    shopping_list = owned_or_today_list(user, list_id=list_id, title=list_title)
    return create_item(shopping_list, name=name, quantity=quantity, department=department)


def _recipe_lines(recipe: Recipe, kind: Literal["ingredient", "step"]) -> Manager:
    """Return the ingredients or steps manager for this recipe."""
    if kind == "ingredient":
        return recipe.ingredients
    if kind == "step":
        return recipe.steps
    raise ServiceError(_("Invalid order."))


def _reorder_owned(manager: Manager, ordered_ids: Sequence[int]) -> None:
    """Require the ids to be exactly these records, then write positions from 1."""
    existing = set(manager.select_for_update().order_by("pk").values_list("pk", flat=True))
    if existing != set(ordered_ids) or len(ordered_ids) != len(existing):
        raise ServiceError(_("Invalid order."))
    for position, record_id in enumerate(ordered_ids, start=1):
        manager.filter(pk=record_id).update(position=position)



def shopping_list_export_data(shopping_list: ShoppingList) -> dict[str, Any]:
    """JSON for one list that Import JSON can read again."""
    return {
        "title": shopping_list.title,
        "icon": shopping_list.icon,
        "date": shopping_list.date.isoformat(),
        "items": [
            {"name": item.name, "quantity": item.quantity, "checked": item.checked, "department": item.department_code}
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
        raise ObjectNotFoundError(_("Recipe not found."))
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
        raise ServiceError(_("This week has no planned recipes yet."))

    if title:
        target = create_shopping_list(user, title=title, date=timezone.localdate())
    elif shopping_list is not None:
        if shopping_list.user_id != user.pk:
            raise ServiceError(_("Invalid shopping list."))
        target = shopping_list
    else:
        raise ServiceError(_("Choose a list or enter a title for a new one."))

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
        raise ServiceError(_("Choose a complete calendar week.")) from None
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
        raise ServiceError(_("Choose exactly one shopping list or a title for a new one."))
    target = None
    if list_id is not None:
        target = user.shopping_lists.filter(pk=list_id).first()
        if target is None:
            raise ObjectNotFoundError(_("Shopping list not found."))
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
