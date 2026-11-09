from __future__ import annotations

import os
import json
from datetime import date as Date
from functools import wraps
from typing import TYPE_CHECKING, Annotated

import django
from django.conf import settings
from django.db import close_old_connections, connections

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

if not settings.configured:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings.production")
    django.setup()

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictBool, StrictInt, create_model
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed
from easy_kitchen.models import ShoppingList
from easy_kitchen.errors import ServiceError
from easy_kitchen.validation import (
    NAME_LIMIT, QUANTITY_LIMIT, DESCRIPTION_LIMIT, STEP_LIMIT, IMAGE_URL_LIMIT,
    COUNT_LIMIT, DEFAULT_LIST_LIMIT, MAX_LIST_LIMIT, clean_count,
)
from easy_kitchen.presenters import (
    recipe_data as _recipe_payload, shopping_list_data as _shopping_list_payload,
    item_data as _item_payload, article_data as _article_payload,
)
from easy_kitchen.services import (
    department_data,
    list_department_data,
    resolve_department as resolve_owned_department,
    add_item_to_owned_list,
    add_meal_plan_to_owned_list,
    add_recipe_to_owned_list,
    clear_meal_plan_day as clear_planned_day,
    meal_plan_day_data,
    meal_plan_week_data,
    plan_owned_recipe,
    update_owned_recipe,
    update_owned_shopping_item,
    update_owned_shopping_list,
    update_owned_article,
    update_owned_department,
    set_owned_recipe_favorite,
    delete_owned_shopping_item,
    delete_completed_items_from_owned_list,
    get_owned_recipe,
    get_owned_shopping_list,
    get_owned_shopping_item,
    get_owned_article,
    get_owned_department,
    delete_owned_recipe,
    delete_owned_shopping_list,
    reorder_shopping_lists as sort_shopping_lists,
    reorder_items as sort_shopping_items,
    reorder_recipes as sort_recipes,
    reorder_recipe_lines as sort_recipe_lines,
    import_recipes as import_recipe_records,
    import_shopping_lists as import_list_records,
    query_owned_recipes,
    query_owned_shopping_lists,
    query_owned_shopping_items,
    query_owned_articles,
)
from easy_kitchen.services import create_recipe as save_recipe
from easy_kitchen.services import create_shopping_list as save_shopping_list
from easy_kitchen.services import set_item_checked as mark_item_checked

class StrictMCPServer(MCPServer):
    """Keep the SDK's generated tool-argument schemas strict at one boundary."""

    def add_tool(self, fn, name=None, **kwargs):
        @wraps(fn)
        def database_call(*args, **call_kwargs):
            # MCP workers do not pass through Django's request/connection lifecycle.
            close_old_connections()
            try:
                return fn(*args, **call_kwargs)
            finally:
                connections.close_all()

        super().add_tool(database_call, name=name, **kwargs)
        tool = self._tool_manager.get_tool(name or fn.__name__)
        base = tool.fn_metadata.arg_model
        strict = create_model(base.__name__, __base__=base, __config__=ConfigDict(extra="forbid", str_strip_whitespace=True))
        tool.fn_metadata.arg_model = strict
        tool.parameters = strict.model_json_schema(by_alias=True)


mcp = StrictMCPServer(
    "EasyKitchen",
    version="0.7.0",
    instructions=(
        "Read and change shopping lists and recipes for the user authenticated by the request token. "
        "Do not invent a user id. Confirm the title, date, and items before creating a list. "
        "List tools return at most 50 records by default; page with limit and offset until a short page when all records are needed. "
        "Use summary=true when searching recipes or shopping lists, then get_recipe or get_shopping_list for full details. "
        "If an ID and a title/name are supplied together, they must identify the same object; conflicting selectors fail. "
        "Confirm the title, ingredients, and steps before creating a recipe. "
        "When checking an item off, use the list the user named, or today's list. "
        "When adding an item, use the named list or today's list; create today's list if none exists. "
        "When adding a recipe to a list, use the named list or today's list; create today's list if none exists. "
        "The meal planner uses one recipe per date; setting a recipe replaces that day's plan. "
        "List departments before assigning one and prefer their stable codes. "
        "Department names and English/German translations accept normalized spacing and conjunctions. "
        "If department_not_found or department_ambiguous is returned, ask the user which department they mean, then retry with the selected candidate code. "
        "Never choose an approximate match or create a department automatically. "
        "Omitting a department keeps the article default; an empty string explicitly clears it. "
        "Use ISO dates. When copying a planned week, provide exactly one existing list_id or "
        "a title for a new list. Copying the week again adds the ingredients again."
    ),
)


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ShoppingItemInput(InputModel):
    """One item to put on a shopping list created through MCP."""

    name: Annotated[str, Field(min_length=1, max_length=NAME_LIMIT)]
    quantity: Annotated[str, Field(max_length=QUANTITY_LIMIT)] = ""
    department: Annotated[str, Field(max_length=NAME_LIMIT)] | None = None
    checked: StrictBool = False
    position: Annotated[StrictInt, Field(ge=0, le=COUNT_LIMIT)] | None = None


class IngredientInput(InputModel):
    """One ingredient to put on a recipe created through MCP."""

    name: Annotated[str, Field(min_length=1, max_length=NAME_LIMIT)]
    quantity: Annotated[str, Field(max_length=QUANTITY_LIMIT)] = ""
    position: Annotated[StrictInt, Field(ge=0, le=COUNT_LIMIT)] | None = None


class StepInput(InputModel):
    """One preparation step to put on a recipe created through MCP."""

    text: Annotated[str, Field(min_length=1, max_length=STEP_LIMIT)]
    position: Annotated[StrictInt, Field(ge=0, le=COUNT_LIMIT)] | None = None


class RecipeUpdateInput(InputModel):
    """Only explicitly supplied fields are changed; null clears numeric values."""

    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, Field(min_length=1, max_length=NAME_LIMIT)] = ""
    description: Annotated[str, Field(max_length=DESCRIPTION_LIMIT)] = ""
    image_url: Annotated[str, Field(max_length=IMAGE_URL_LIMIT)] = ""
    calories: Annotated[int, Field(ge=0, le=COUNT_LIMIT), BeforeValidator(clean_count)] | None = None
    protein: Annotated[int, Field(ge=0, le=COUNT_LIMIT), BeforeValidator(clean_count)] | None = None
    carbohydrates: Annotated[int, Field(ge=0, le=COUNT_LIMIT), BeforeValidator(clean_count)] | None = None
    fat: Annotated[int, Field(ge=0, le=COUNT_LIMIT), BeforeValidator(clean_count)] | None = None
    preparation_minutes: Annotated[int, Field(ge=0, le=COUNT_LIMIT), BeforeValidator(clean_count)] | None = None
    ingredients: list[IngredientInput] = Field(default_factory=list)
    steps: list[StepInput] = Field(default_factory=list)


class NamedUpdateInput(InputModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[str, Field(min_length=1, max_length=NAME_LIMIT)] = ""


class ArticleUpdateInput(NamedUpdateInput):
    department: Annotated[str, Field(max_length=NAME_LIMIT)] = ""


class ShoppingItemUpdateInput(ArticleUpdateInput):
    quantity: Annotated[str, Field(max_length=QUANTITY_LIMIT)] = ""
    checked: StrictBool = False


class DepartmentUpdateInput(NamedUpdateInput):
    name: Annotated[str, Field(min_length=1, max_length=QUANTITY_LIMIT)] = ""


class ShoppingListUpdateInput(InputModel):
    model_config = ConfigDict(extra="forbid")
    title: Annotated[str, Field(min_length=1, max_length=NAME_LIMIT)] = ""
    date: Date = Date.min
    icon: ShoppingList.Icon = ShoppingList.Icon.BASKET
    items: list[ShoppingItemInput] = Field(default_factory=list)


class RecipeImportInput(RecipeUpdateInput):
    title: Annotated[str, Field(min_length=1, max_length=NAME_LIMIT)]


class ShoppingListImportInput(InputModel):
    title: Annotated[str, Field(min_length=1, max_length=NAME_LIMIT)]
    date: Date = Field(default_factory=timezone.localdate)
    icon: ShoppingList.Icon = ShoppingList.Icon.BASKET
    items: list[ShoppingItemInput] = Field(default_factory=list)


RecordID = Annotated[StrictInt, Field(ge=1)]
ResultLimit = Annotated[StrictInt, Field(ge=1, le=MAX_LIST_LIMIT)]
ResultOffset = Annotated[StrictInt, Field(ge=0, le=COUNT_LIMIT)]


def _allowed_hosts() -> list[str]:
    """Hosts allowed to call the MCP server, from the environment or local defaults."""
    configured = os.environ.get("MCP_ALLOWED_HOSTS", "")
    hosts = [item.strip() for item in configured.split(",") if item.strip()]
    if hosts:
        return hosts
    hosts = ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"]
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(","):
        host = host.strip()
        if host:
            hosts.extend((host, f"{host}:*"))
    return hosts


def _allowed_origins() -> list[str]:
    """Origins allowed to call the MCP server, from the environment or local defaults."""
    configured = os.environ.get("MCP_ALLOWED_ORIGINS", "")
    origins = [item.strip() for item in configured.split(",") if item.strip()]
    if origins:
        return origins
    origins = ["http://localhost", "http://localhost:*", "http://127.0.0.1", "http://127.0.0.1:*"]
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(","):
        origin = origin.strip()
        if origin:
            origins.append(origin)
    return origins


def _authorization(ctx: Context) -> str | None:
    """Read the Authorization header from the MCP request, if one was sent."""
    request = ctx.request_context.request
    if request is None:
        return None
    return request.headers.get("authorization")


def _tool_error(error):
    detail = error.as_dict() if isinstance(error, ServiceError) else {"code": "invalid_input", "message": str(error)}
    return ToolError(json.dumps(detail, ensure_ascii=False))


def _run_update(ctx, changes, input_model, operation, **selection):
    user = user_from_authorization(_authorization(ctx))
    try:
        values = input_model.model_validate(changes).model_dump(exclude_unset=True)
        return operation(user, changes=values, **selection)
    except ValueError as error:
        raise _tool_error(error) from None


def _run_operation(ctx, operation, **selection):
    user = user_from_authorization(_authorization(ctx))
    try:
        return operation(user, **selection)
    except ValueError as error:
        raise _tool_error(error) from None


def _reorder_roots(ctx, ids, *, recipes):
    def operation(user):
        if recipes:
            sort_recipes(user, ids)
            return [_recipe_payload(recipe) for recipe in user.recipes.prefetch_related("ingredients", "steps")]
        sort_shopping_lists(user, ids)
        return [_shopping_list_payload(shopping_list) for shopping_list in user.shopping_lists.prefetch_related("items__department")]

    return _run_operation(ctx, operation)


def _reorder_recipe_children(ctx, recipe_id, line_ids, kind):
    def operation(user):
        recipe = get_owned_recipe(user, recipe_id=recipe_id)
        sort_recipe_lines(recipe, kind, line_ids)
        recipe.refresh_from_db()
        return _recipe_payload(recipe)

    return _run_operation(ctx, operation)


def user_from_authorization(authorization: str | None) -> AbstractBaseUser:
    """Resolve the EasyKitchen user from an Authorization: Token header."""
    message = "Send the user's EasyKitchen token in the Authorization header: Token <token>."
    if not authorization or not authorization.lower().startswith("token "):
        raise ToolError(message)
    key = authorization.split(" ", 1)[1].strip()
    if not key:
        raise ToolError(message)
    try:
        user, _token = TokenAuthentication().authenticate_credentials(key)
    except AuthenticationFailed:
        raise ToolError("The EasyKitchen token is invalid.") from None
    return user


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    )
)
def create_shopping_list(
    title: Annotated[str, Field(min_length=1, max_length=NAME_LIMIT)],
    date: Date,
    ctx: Context,
    items: list[ShoppingItemInput] | None = None,
    icon: Annotated[str, Field(max_length=20)] = "",
) -> dict:
    """Create a shopping list for the authenticated user."""
    user = user_from_authorization(_authorization(ctx))
    normalized_items = [ShoppingItemInput.model_validate(item) for item in items or []]
    try:
        shopping_list = save_shopping_list(
            user,
            title=title.strip(),
            date=date,
            icon=icon,
            items=[item.model_dump(exclude_none=True) for item in normalized_items],
        )
    except ValueError as error:
        raise _tool_error(error) from None
    return _shopping_list_payload(shopping_list)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    )
)
def create_recipe(
    title: Annotated[str, Field(min_length=1, max_length=NAME_LIMIT)],
    ctx: Context,
    description: Annotated[str, Field(max_length=DESCRIPTION_LIMIT)] = "",
    image_url: Annotated[str, Field(max_length=IMAGE_URL_LIMIT)] = "",
    calories: Annotated[int, Field(ge=0, le=COUNT_LIMIT), BeforeValidator(clean_count)] | None = None,
    protein: Annotated[int, Field(ge=0, le=COUNT_LIMIT), BeforeValidator(clean_count)] | None = None,
    carbohydrates: Annotated[int, Field(ge=0, le=COUNT_LIMIT), BeforeValidator(clean_count)] | None = None,
    fat: Annotated[int, Field(ge=0, le=COUNT_LIMIT), BeforeValidator(clean_count)] | None = None,
    preparation_minutes: Annotated[int, Field(ge=0, le=COUNT_LIMIT), BeforeValidator(clean_count)] | None = None,
    ingredients: list[IngredientInput] | None = None,
    steps: list[StepInput] | None = None,
) -> dict:
    """Create a recipe for the authenticated user. image_url, calories, protein, carbohydrates, fat, and preparation_minutes are optional."""
    user = user_from_authorization(_authorization(ctx))
    try:
        recipe = save_recipe(
            user,
            title=title,
            description=description,
            image_url=image_url,
            calories=calories,
            protein=protein,
            carbohydrates=carbohydrates,
            fat=fat,
            preparation_minutes=preparation_minutes,
            ingredients=[IngredientInput.model_validate(item).model_dump() for item in ingredients or []],
            steps=[StepInput.model_validate(item).model_dump() for item in steps or []],
        )
    except ValueError as error:
        raise _tool_error(error) from None
    return _recipe_payload(recipe)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=True,
        open_world_hint=False,
    )
)
def update_recipe(
    ctx: Context,
    changes: RecipeUpdateInput,
    recipe_id: Annotated[int, Field(ge=1)] | None = None,
    recipe_title: Annotated[str, Field(max_length=NAME_LIMIT)] = "",
) -> dict:
    """Edit an owned recipe by id or unique title. Omitted changes are preserved. Null clears numeric values; empty strings clear description/image_url. Supplied ingredients/steps replace the entire collection; [] clears it."""
    return _recipe_payload(_run_update(ctx, changes, RecipeUpdateInput, update_owned_recipe,
                                      recipe_id=recipe_id, recipe_title=recipe_title))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False))
def update_shopping_item(item_id: Annotated[int, Field(ge=1)], changes: ShoppingItemUpdateInput, ctx: Context) -> dict:
    """Edit an owned shopping item by ID. Only supplied fields change; quantity replaces the old quantity. Empty quantity/department clears it. Checked state is preserved unless supplied."""
    return _item_payload(_run_update(ctx, changes, ShoppingItemUpdateInput, update_owned_shopping_item, item_id=item_id))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False))
def update_shopping_list(list_id: Annotated[int, Field(ge=1)], changes: ShoppingListUpdateInput, ctx: Context) -> dict:
    """Edit an owned list's title, ISO date, icon or items. Omitted fields are preserved. Supplied items replace the collection; [] clears it. Never creates a list."""
    return _shopping_list_payload(_run_update(ctx, changes, ShoppingListUpdateInput, update_owned_shopping_list, list_id=list_id))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
def list_articles(
    ctx: Context, q: Annotated[str, Field(max_length=NAME_LIMIT)] = "",
    department: Annotated[str, Field(max_length=NAME_LIMIT)] | None = None,
    limit: ResultLimit = DEFAULT_LIST_LIMIT, offset: ResultOffset = 0,
) -> list[dict]:
    """Search owned article names and filter by department code/name (empty means unassigned). Returns a bounded page; use offset for further pages."""
    records = _run_operation(ctx, query_owned_articles, q=q, department=department, limit=limit, offset=offset)
    return [_article_payload(article) for article in records]


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False))
def update_article(article_id: Annotated[int, Field(ge=1)], changes: ArticleUpdateInput, ctx: Context) -> dict:
    """Edit an owned article's name or default department. Omitted fields and existing list entries are preserved. Empty department clears it."""
    return _article_payload(_run_update(ctx, changes, ArticleUpdateInput, update_owned_article, article_id=article_id))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False))
def update_department(department_id: Annotated[int, Field(ge=1)], changes: DepartmentUpdateInput, ctx: Context) -> dict:
    """Rename an owned department by ID. Its stable code, position and article/item references are preserved."""
    return department_data(_run_update(ctx, changes, DepartmentUpdateInput, update_owned_department, department_id=department_id))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False))
def set_recipe_favorite(
    is_favorite: StrictBool, ctx: Context,
    recipe_id: Annotated[int, Field(ge=1)] | None = None,
    recipe_title: Annotated[str, Field(max_length=NAME_LIMIT)] = "",
) -> dict:
    """Set an owned recipe's favorite state to true or false by ID or unique title. Repeated calls preserve the requested state."""
    user = user_from_authorization(_authorization(ctx))
    try:
        recipe = set_owned_recipe_favorite(user, is_favorite=is_favorite, recipe_id=recipe_id, recipe_title=recipe_title)
    except ValueError as error:
        raise _tool_error(error) from None
    return _recipe_payload(recipe)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False))
def delete_shopping_item(item_id: Annotated[int, Field(ge=1)], ctx: Context) -> dict:
    """Delete an owned shopping-list entry by ID. Its list and saved article remain. Missing or foreign IDs return an error."""
    user = user_from_authorization(_authorization(ctx))
    try:
        delete_owned_shopping_item(user, item_id=item_id)
    except ValueError as error:
        raise _tool_error(error) from None
    return {"item_id": item_id, "deleted": True}


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False))
def delete_completed_items(list_id: Annotated[int, Field(ge=1)], ctx: Context) -> dict:
    """Delete checked entries from an existing owned list. Return the deleted count; open entries and saved articles remain. Repeating on an unchanged list deletes zero."""
    user = user_from_authorization(_authorization(ctx))
    try:
        count = delete_completed_items_from_owned_list(user, list_id=list_id)
    except ValueError as error:
        raise _tool_error(error) from None
    return {"list_id": list_id, "deleted_count": count}


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )
)
def list_shopping_lists(
    ctx: Context, q: Annotated[str, Field(max_length=NAME_LIMIT)] = "",
    date_from: Date | None = None, date_to: Date | None = None,
    limit: ResultLimit = DEFAULT_LIST_LIMIT, offset: ResultOffset = 0, summary: StrictBool = False,
) -> list[dict]:
    """Search owned list titles and inclusive ISO date ranges. Returns a bounded page. Use summary=true to omit items, then get_shopping_list for details."""
    records = _run_operation(ctx, query_owned_shopping_lists, q=q, date_from=date_from, date_to=date_to,
                             limit=limit, offset=offset, summary=summary)
    return [_shopping_list_payload(record, summary=summary) for record in records]


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
def list_departments(
    ctx: Context, q: Annotated[str, Field(max_length=NAME_LIMIT)] = "",
    limit: ResultLimit = DEFAULT_LIST_LIMIT, offset: ResultOffset = 0,
) -> list[dict]:
    """Search owned department codes, names and translated labels. Returns a bounded page sorted by label. Prefer returned stable codes for writes."""
    return _run_operation(ctx, list_department_data, q=q, limit=limit, offset=offset)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
def resolve_department(name: Annotated[str, Field(min_length=1, max_length=NAME_LIMIT)], ctx: Context) -> dict:
    """Resolve an owned department code/name/translation without writing. Ask the user to choose when candidates are returned."""
    user = user_from_authorization(_authorization(ctx))
    if not name.strip():
        raise ToolError(_("Enter a department name."))
    try:
        department = resolve_owned_department(user, name)
    except ValueError as error:
        raise _tool_error(error) from None
    return department_data(department)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )
)
def list_recipes(
    ctx: Context, q: Annotated[str, Field(max_length=NAME_LIMIT)] = "", is_favorite: StrictBool | None = None,
    limit: ResultLimit = DEFAULT_LIST_LIMIT, offset: ResultOffset = 0, summary: StrictBool = False,
) -> list[dict]:
    """Search owned recipe titles, descriptions and ingredients; optionally filter favorite state. Returns a bounded page. Use summary=true to omit ingredients/steps, then get_recipe for details."""
    records = _run_operation(ctx, query_owned_recipes, q=q, is_favorite=is_favorite,
                             limit=limit, offset=offset, summary=summary)
    return [_recipe_payload(recipe, summary=summary) for recipe in records]


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
def get_recipe(recipe_id: RecordID, ctx: Context) -> dict:
    """Read one owned recipe by ID, including ingredients, steps, nutrition and image metadata."""
    return _recipe_payload(_run_operation(ctx, get_owned_recipe, recipe_id=recipe_id))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
def get_shopping_list(list_id: RecordID, ctx: Context) -> dict:
    """Read one existing owned shopping list by ID, including its items. Never creates a list."""
    return _shopping_list_payload(_run_operation(ctx, get_owned_shopping_list, list_id=list_id))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
def get_shopping_item(item_id: RecordID, ctx: Context) -> dict:
    """Read one entry of an owned shopping list by its item ID."""
    return _item_payload(_run_operation(ctx, get_owned_shopping_item, item_id=item_id))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
def get_article(article_id: RecordID, ctx: Context) -> dict:
    """Read one owned saved article by ID, including its default department code."""
    return _article_payload(_run_operation(ctx, get_owned_article, article_id=article_id))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
def get_department(department_id: RecordID, ctx: Context) -> dict:
    """Read one owned department by ID, including its stable code, name and translated label."""
    return department_data(_run_operation(ctx, get_owned_department, department_id=department_id))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
def list_shopping_items(
    ctx: Context, q: Annotated[str, Field(max_length=NAME_LIMIT)] = "", checked: StrictBool | None = None,
    list_id: RecordID | None = None, limit: ResultLimit = DEFAULT_LIST_LIMIT, offset: ResultOffset = 0,
) -> list[dict]:
    """Search owned entry names, optionally filtering checked state and an owned list_id. Returns a bounded page across shopping lists with list IDs."""
    records = _run_operation(ctx, query_owned_shopping_items, q=q, checked=checked, list_id=list_id,
                             limit=limit, offset=offset)
    return [_item_payload(item) for item in records]


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False))
def delete_recipe(recipe_id: RecordID, ctx: Context) -> dict:
    """Delete an owned recipe, its ingredients/steps and meal-plan references. Shopping lists remain. Missing/foreign IDs are errors."""
    _run_operation(ctx, delete_owned_recipe, recipe_id=recipe_id)
    return {"recipe_id": recipe_id, "deleted": True}


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False))
def delete_shopping_list(list_id: RecordID, ctx: Context) -> dict:
    """Delete an owned shopping list and its entries. Saved articles and recipes remain. Missing/foreign IDs are errors."""
    _run_operation(ctx, delete_owned_shopping_list, list_id=list_id)
    return {"list_id": list_id, "deleted": True}


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False))
def reorder_shopping_lists(list_ids: list[RecordID], ctx: Context) -> list[dict]:
    """Order all owned lists. Pass every current list ID exactly once in the desired order; returns ordered lists."""
    return _reorder_roots(ctx, list_ids, recipes=False)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False))
def reorder_recipes(recipe_ids: list[RecordID], ctx: Context) -> list[dict]:
    """Order all owned recipes. Pass every current recipe ID exactly once in the desired order; returns ordered recipes."""
    return _reorder_roots(ctx, recipe_ids, recipes=True)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False))
def reorder_shopping_items(list_id: RecordID, item_ids: list[RecordID], ctx: Context) -> dict:
    """Order one owned list's entries. Pass every current item ID exactly once; returns the updated list."""
    def operation(user):
        shopping_list = get_owned_shopping_list(user, list_id=list_id)
        sort_shopping_items(shopping_list, item_ids)
        shopping_list.refresh_from_db()
        return _shopping_list_payload(shopping_list)

    return _run_operation(ctx, operation)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False))
def reorder_recipe_ingredients(recipe_id: RecordID, line_ids: list[RecordID], ctx: Context) -> dict:
    """Order an owned recipe's ingredients. Pass every current ingredient ID exactly once; returns the updated recipe."""
    return _reorder_recipe_children(ctx, recipe_id, line_ids, "ingredient")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False))
def reorder_recipe_steps(recipe_id: RecordID, line_ids: list[RecordID], ctx: Context) -> dict:
    """Order an owned recipe's steps. Pass every current step ID exactly once; returns the updated recipe."""
    return _reorder_recipe_children(ctx, recipe_id, line_ids, "step")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False))
def import_recipes(recipes: list[RecipeImportInput], ctx: Context) -> list[dict]:
    """Create a batch of owned recipes at the front in input order. Confirm records first. All-or-nothing; repeating creates additional recipes."""
    def operation(user):
        records = [RecipeImportInput.model_validate(record).model_dump(exclude_none=True) for record in recipes]
        return [_recipe_payload(recipe) for recipe in import_recipe_records(user, records)]

    return _run_operation(ctx, operation)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False))
def import_shopping_lists(lists: list[ShoppingListImportInput], ctx: Context) -> list[dict]:
    """Create a batch of owned shopping lists at the front in input order. Confirm records first. All-or-nothing; repeating creates additional lists."""
    def operation(user):
        records = [ShoppingListImportInput.model_validate(record).model_dump(exclude_none=True) for record in lists]
        return [_shopping_list_payload(shopping_list) for shopping_list in import_list_records(user, records)]

    return _run_operation(ctx, operation)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )
)
def set_item_checked(
    ctx: Context,
    name: Annotated[str, Field(max_length=NAME_LIMIT)] = "",
    checked: StrictBool = True,
    list_id: Annotated[int, Field(ge=1)] | None = None,
    item_id: Annotated[int, Field(ge=1)] | None = None,
) -> dict:
    """Set checked state by owned item_id (preferred), or an unambiguous name and optional list_id. Never choose an arbitrary duplicate."""
    user = user_from_authorization(_authorization(ctx))
    try:
        item = mark_item_checked(user, name=name, checked=checked, list_id=list_id, item_id=item_id)
    except ValueError as error:
        raise _tool_error(error) from None
    return _item_payload(item)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    )
)
def add_item_to_list(
    name: Annotated[str, Field(min_length=1, max_length=NAME_LIMIT)],
    ctx: Context,
    quantity: Annotated[str, Field(max_length=QUANTITY_LIMIT)] = "",
    list_id: Annotated[int, Field(ge=1)] | None = None,
    list_title: Annotated[str, Field(max_length=NAME_LIMIT)] = "",
    department: Annotated[str, Field(max_length=NAME_LIMIT)] | None = None,
) -> dict:
    """Add an item to a list. Omit the list to use or create today's list."""
    user = user_from_authorization(_authorization(ctx))
    try:
        item = add_item_to_owned_list(
            user,
            name=name,
            quantity=quantity,
            list_id=list_id,
            list_title=list_title,
            department=department,
        )
    except ValueError as error:
        raise _tool_error(error) from None
    return _item_payload(item)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    )
)
def add_recipe_to_list(
    ctx: Context,
    recipe_id: Annotated[int, Field(ge=1)] | None = None,
    recipe_title: Annotated[str, Field(max_length=NAME_LIMIT)] = "",
    list_id: Annotated[int, Field(ge=1)] | None = None,
    list_title: Annotated[str, Field(max_length=NAME_LIMIT)] = "",
) -> dict:
    """Copy a recipe's ingredients onto a list. Omit the list to use or create today's list."""
    user = user_from_authorization(_authorization(ctx))
    try:
        shopping_list = add_recipe_to_owned_list(
            user,
            recipe_id=recipe_id,
            recipe_title=recipe_title,
            list_id=list_id,
            list_title=list_title,
        )
    except ValueError as error:
        raise _tool_error(error) from None
    return _shopping_list_payload(shopping_list)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )
)
def get_meal_plan_week(ctx: Context, week: Date | None = None) -> dict:
    """Read a Monday–Sunday plan with seven days. Omit week for the current local week."""
    user = user_from_authorization(_authorization(ctx))
    try:
        return meal_plan_week_data(user, week)
    except ValueError as error:
        raise _tool_error(error) from None


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=True,
        open_world_hint=False,
    )
)
def set_meal_plan_recipe(
    date: Date,
    ctx: Context,
    recipe_id: Annotated[int, Field(ge=1)] | None = None,
    recipe_title: Annotated[str, Field(max_length=NAME_LIMIT)] = "",
) -> dict:
    """Plan an owned recipe by id or unique title. Replaces any existing recipe on this date."""
    user = user_from_authorization(_authorization(ctx))
    try:
        return plan_owned_recipe(user, date, recipe_id=recipe_id, recipe_title=recipe_title)
    except ValueError as error:
        raise _tool_error(error) from None


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=True,
        open_world_hint=False,
    )
)
def clear_meal_plan_day(date: Date, ctx: Context) -> dict:
    """Remove the authenticated user's planned recipe for a date. An empty day is unchanged."""
    user = user_from_authorization(_authorization(ctx))
    clear_planned_day(user, date)
    return meal_plan_day_data(date)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    )
)
def add_meal_plan_week_to_list(
    week: Date,
    ctx: Context,
    list_id: Annotated[int, Field(ge=1)] | None = None,
    title: Annotated[str, Field(max_length=NAME_LIMIT)] = "",
) -> dict:
    """Copy a week's ingredients to list_id OR a new list named title. Repeated calls add quantities again."""
    user = user_from_authorization(_authorization(ctx))
    try:
        target = add_meal_plan_to_owned_list(user, week, list_id=list_id, title=title)
    except ValueError as error:
        raise _tool_error(error) from None
    return _shopping_list_payload(target)


def main() -> None:
    """Refuse to start while migrations are unapplied, then serve the MCP endpoint."""
    from easy_kitchen.startup import ensure_migrations_applied

    ensure_migrations_applied()
    mcp.run(
        transport="streamable-http",
        host=os.environ.get("MCP_HOST", "0.0.0.0"),
        port=int(os.environ.get("MCP_PORT", "8001")),
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=_allowed_hosts(),
            allowed_origins=_allowed_origins(),
        ),
    )


if __name__ == "__main__":
    main()
