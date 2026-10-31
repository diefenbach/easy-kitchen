from datetime import date
from types import SimpleNamespace

import pytest
from mcp.server.context import ServerRequestContext
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from rest_framework.authtoken.models import Token
from shopping.mcp_server import create_shopping_list, mcp
from shopping.models import ShoppingList


def authorization_context(token):
    request = SimpleNamespace(headers={"authorization": f"Token {token.key}"})
    return Context(
        mcp_server=mcp,
        request_context=ServerRequestContext(
            session=None,
            lifespan_context={},
            protocol_version="2025-06-18",
            method="tools/call",
            request=request,
        ),
    )


@pytest.mark.django_db
def test_mcp_creates_a_list_for_the_token_owner(user, other_user):
    token = Token.objects.create(user=user)
    Token.objects.create(user=other_user)

    result = create_shopping_list(
        title="Pasta",
        date=date(2026, 10, 31),
        items=[],
        ctx=authorization_context(token),
    )

    shopping_list = ShoppingList.objects.get(pk=result["id"])
    assert shopping_list.user == user
    assert result["title"] == "Pasta"
    assert result["date"] == "2026-10-31"
    assert ShoppingList.objects.filter(user=other_user).count() == 0


@pytest.mark.django_db
def test_mcp_stores_items_on_the_new_list(user):
    token = Token.objects.create(user=user)

    result = create_shopping_list(
        title="Pasta",
        date=date(2026, 10, 31),
        items=[{"name": "Nudeln", "quantity": "500 g"}],
        ctx=authorization_context(token),
    )

    assert [(item["name"], item["quantity"]) for item in result["items"]] == [("Nudeln", "500 g")]


@pytest.mark.django_db
def test_mcp_rejects_a_missing_or_unknown_token(user):
    with pytest.raises(ToolError):
        create_shopping_list(title="Pasta", date=date(2026, 10, 31), ctx=authorization_context(Token(key="missing")))

    request = SimpleNamespace(headers={})
    context = Context(
        mcp_server=mcp,
        request_context=ServerRequestContext(
            session=None,
            lifespan_context={},
            protocol_version="2025-06-18",
            method="tools/call",
            request=request,
        ),
    )
    with pytest.raises(ToolError):
        create_shopping_list(title="Pasta", date=date(2026, 10, 31), ctx=context)


def test_mcp_create_tool_does_not_accept_a_user_argument():
    tool = next(tool for tool in mcp._tool_manager.list_tools() if tool.name == "create_shopping_list")
    assert set(tool.parameters["properties"]) == {"title", "date", "items"}
