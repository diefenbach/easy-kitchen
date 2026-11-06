from __future__ import annotations

import os
from datetime import date as Date
from typing import TYPE_CHECKING, Annotated

import django
from django.conf import settings

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

if not settings.configured:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings.production")
    django.setup()

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed
from easy_kitchen.models import Recipe, ShoppingList
from easy_kitchen.services import (
    add_item_to_owned_list,
    add_meal_plan_to_owned_list,
    add_recipe_to_owned_list,
    clear_meal_plan_day as clear_planned_day,
    meal_plan_day_data,
    meal_plan_week_data,
    plan_owned_recipe,
)
from easy_kitchen.services import create_recipe as save_recipe
from easy_kitchen.services import create_shopping_list as save_shopping_list
from easy_kitchen.services import set_item_checked as mark_item_checked

mcp = MCPServer(
    "EasyKitchen",
    version="0.7.0",
    instructions=(
        "Read and change shopping lists and recipes for the user authenticated by the request token. "
        "Do not invent a user id. Confirm the title, date, and items before creating a list. "
        "Confirm the title, ingredients, and steps before creating a recipe. "
        "When checking an item off, use the list the user named, or today's list. "
        "When adding an item, use the named list or today's list; create today's list if none exists. "
        "When adding a recipe to a list, use the named list or today's list; create today's list if none exists. "
        "The meal planner uses one recipe per date; setting a recipe replaces that day's plan. "
        "Use ISO dates. When copying a planned week, provide exactly one existing list_id or "
        "a title for a new list. Copying the week again adds the ingredients again."
    ),
)


class ShoppingItemInput(BaseModel):
    """One item to put on a shopping list created through MCP."""

    name: Annotated[str, Field(min_length=1, max_length=255)]
    quantity: Annotated[str, Field(max_length=100)] = ""
    department: Annotated[str, Field(max_length=20)] | None = None


class IngredientInput(BaseModel):
    """One ingredient to put on a recipe created through MCP."""

    name: Annotated[str, Field(min_length=1, max_length=255)]
    quantity: Annotated[str, Field(max_length=100)] = ""


class StepInput(BaseModel):
    """One preparation step to put on a recipe created through MCP."""

    text: Annotated[str, Field(min_length=1, max_length=2000)]


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


def _shopping_list_payload(shopping_list: ShoppingList) -> dict:
    """JSON for one list, including item ids so later tools can name them."""
    return {
        "id": shopping_list.id,
        "title": shopping_list.title,
        "icon": shopping_list.icon,
        "date": shopping_list.date.isoformat(),
        "items": [
            {
                "id": item.id,
                "name": item.name,
                "quantity": item.quantity,
                "department": item.department_code,
                "checked": item.checked,
            }
            for item in shopping_list.items.all()
        ],
    }


def _recipe_payload(recipe: Recipe) -> dict:
    """JSON for one recipe, including ingredients and steps."""
    return {
        "id": recipe.id,
        "title": recipe.title,
        "description": recipe.description,
        "image_url": recipe.image_url,
        "calories": recipe.calories,
        "protein": recipe.protein,
        "carbohydrates": recipe.carbohydrates,
        "fat": recipe.fat,
        "preparation_minutes": recipe.preparation_minutes,
        "ingredients": [{"name": line.name, "quantity": line.quantity} for line in recipe.ingredients.all()],
        "steps": [{"text": line.text} for line in recipe.steps.all()],
    }


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
    title: Annotated[str, Field(min_length=1, max_length=255)],
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
            items=[item.model_dump() for item in normalized_items],
        )
    except ValueError as error:
        raise ToolError(str(error)) from None
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
    title: Annotated[str, Field(min_length=1, max_length=255)],
    ctx: Context,
    description: Annotated[str, Field(max_length=5000)] = "",
    image_url: Annotated[str, Field(max_length=500)] = "",
    calories: Annotated[int, Field(ge=0)] | None = None,
    protein: Annotated[int, Field(ge=0)] | None = None,
    carbohydrates: Annotated[int, Field(ge=0)] | None = None,
    fat: Annotated[int, Field(ge=0)] | None = None,
    preparation_minutes: Annotated[int, Field(ge=0)] | None = None,
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
        raise ToolError(str(error)) from None
    return _recipe_payload(recipe)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )
)
def list_shopping_lists(ctx: Context) -> list[dict]:
    """List the authenticated user's shopping lists and their items."""
    user = user_from_authorization(_authorization(ctx))
    return [_shopping_list_payload(shopping_list) for shopping_list in user.shopping_lists.prefetch_related("items__department")]


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )
)
def list_recipes(ctx: Context) -> list[dict]:
    """List the authenticated user's recipes, including ingredients and steps."""
    user = user_from_authorization(_authorization(ctx))
    return [_recipe_payload(recipe) for recipe in user.recipes.prefetch_related("ingredients", "steps")]


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )
)
def set_item_checked(
    name: Annotated[str, Field(min_length=1, max_length=255)],
    ctx: Context,
    checked: bool = True,
    list_id: int | None = None,
) -> dict:
    """Mark an item completed or open. Use list_id when the name is on more than one list."""
    user = user_from_authorization(_authorization(ctx))
    try:
        item = mark_item_checked(user, name=name, checked=checked, list_id=list_id)
    except ValueError as error:
        raise ToolError(str(error)) from None
    return {
        "id": item.id,
        "name": item.name,
        "quantity": item.quantity,
        "department": item.department_code,
        "checked": item.checked,
        "list_id": item.shopping_list_id,
    }


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    )
)
def add_item_to_list(
    name: Annotated[str, Field(min_length=1, max_length=255)],
    ctx: Context,
    quantity: Annotated[str, Field(max_length=100)] = "",
    list_id: int | None = None,
    list_title: Annotated[str, Field(max_length=255)] = "",
    department: Annotated[str, Field(max_length=20)] | None = None,
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
        raise ToolError(str(error)) from None
    return {
        "id": item.id,
        "name": item.name,
        "quantity": item.quantity,
        "department": item.department_code,
        "checked": item.checked,
        "list_id": item.shopping_list_id,
    }


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
    recipe_id: int | None = None,
    recipe_title: Annotated[str, Field(max_length=255)] = "",
    list_id: int | None = None,
    list_title: Annotated[str, Field(max_length=255)] = "",
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
        raise ToolError(str(error)) from None
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
        raise ToolError(str(error)) from None


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
    recipe_title: Annotated[str, Field(max_length=255)] = "",
) -> dict:
    """Plan an owned recipe by id or unique title. Replaces any existing recipe on this date."""
    user = user_from_authorization(_authorization(ctx))
    try:
        return plan_owned_recipe(user, date, recipe_id=recipe_id, recipe_title=recipe_title)
    except ValueError as error:
        raise ToolError(str(error)) from None


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
    title: Annotated[str, Field(max_length=255)] = "",
) -> dict:
    """Copy a week's ingredients to list_id OR a new list named title. Repeated calls add quantities again."""
    user = user_from_authorization(_authorization(ctx))
    try:
        target = add_meal_plan_to_owned_list(user, week, list_id=list_id, title=title)
    except ValueError as error:
        raise ToolError(str(error)) from None
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
