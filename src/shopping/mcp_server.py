import os
from datetime import date as Date
from typing import Annotated

import django
from django.conf import settings

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
from shopping.services import create_recipe as save_recipe
from shopping.services import create_shopping_list as save_shopping_list

mcp = MCPServer(
    "EasyList",
    version="0.5.0",
    instructions=(
        "Create shopping lists and recipes for the user authenticated by the request token. "
        "Do not invent a user id. Confirm the title, date, and items before creating a list. "
        "Confirm the title, ingredients, and steps before creating a recipe."
    ),
)


class ShoppingItemInput(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=255)]
    quantity: Annotated[str, Field(max_length=100)] = ""


class IngredientInput(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=255)]
    quantity: Annotated[str, Field(max_length=100)] = ""


class StepInput(BaseModel):
    text: Annotated[str, Field(min_length=1, max_length=2000)]


def _allowed_hosts() -> list[str]:
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
    request = ctx.request_context.request
    if request is None:
        return None
    return request.headers.get("authorization")


def user_from_authorization(authorization: str | None):
    message = "Send the user's EasyList token in the Authorization header: Token <token>."
    if not authorization or not authorization.lower().startswith("token "):
        raise ToolError(message)
    key = authorization.split(" ", 1)[1].strip()
    if not key:
        raise ToolError(message)
    try:
        user, _token = TokenAuthentication().authenticate_credentials(key)
    except AuthenticationFailed:
        raise ToolError("The EasyList token is invalid.") from None
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
) -> dict:
    """Create a shopping list for the authenticated user."""
    user = user_from_authorization(_authorization(ctx))
    normalized_items = [ShoppingItemInput.model_validate(item) for item in items or []]
    shopping_list = save_shopping_list(
        user,
        title=title.strip(),
        date=date,
        items=[item.model_dump() for item in normalized_items],
    )
    return {
        "id": shopping_list.id,
        "title": shopping_list.title,
        "date": shopping_list.date.isoformat(),
        "items": [
            {"id": item.id, "name": item.name, "quantity": item.quantity}
            for item in shopping_list.items.all()
        ],
    }


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
    ingredients: list[IngredientInput] | None = None,
    steps: list[StepInput] | None = None,
) -> dict:
    """Create a recipe for the authenticated user. image_url is optional; upload the picture in the web app."""
    user = user_from_authorization(_authorization(ctx))
    try:
        recipe = save_recipe(
            user,
            title=title,
            description=description,
            image_url=image_url,
            ingredients=[IngredientInput.model_validate(item).model_dump() for item in ingredients or []],
            steps=[StepInput.model_validate(item).model_dump() for item in steps or []],
        )
    except ValueError as error:
        raise ToolError(str(error)) from None
    return {
        "id": recipe.id,
        "title": recipe.title,
        "description": recipe.description,
        "image_url": recipe.image_url,
        "ingredients": [
            {"id": line.id, "name": line.name, "quantity": line.quantity} for line in recipe.ingredients.all()
        ],
        "steps": [{"id": line.id, "text": line.text} for line in recipe.steps.all()],
    }


def main() -> None:
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
