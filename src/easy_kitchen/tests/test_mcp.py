from datetime import date
from types import SimpleNamespace

import pytest
from django.utils import timezone, translation
from mcp.server.context import ServerRequestContext
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from rest_framework.authtoken.models import Token
from easy_kitchen.mcp_server import (
    add_item_to_list,
    add_recipe_to_list,
    create_recipe,
    create_shopping_list,
    list_recipes,
    list_shopping_lists,
    mcp,
    set_item_checked,
)
from easy_kitchen.models import Recipe, ShoppingItem, ShoppingList
from easy_kitchen.services import create_recipe as save_recipe
from easy_kitchen.services import create_shopping_list as save_shopping_list


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
def test_quantity_overflow_is_a_tool_error_and_preserves_existing_data(user):
    token = Token.objects.create(user=user)
    shopping_list = save_shopping_list(
        user, title="Shop", date=date.today(),
        items=[{"name": "Milk", "quantity": "1 " + "a" * 98}],
    )
    with pytest.raises(ToolError, match="100"):
        add_item_to_list(
            name="Milk", quantity="1 " + "b" * 98, list_id=shopping_list.pk,
            ctx=authorization_context(token),
        )
    assert shopping_list.items.get().quantity == "1 " + "a" * 98


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
    assert result["icon"] == "basket"
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
    assert set(tool.parameters["properties"]) == {"title", "date", "items", "icon"}


@pytest.mark.django_db
def test_mcp_creates_a_recipe_for_the_token_owner(user, other_user):
    token = Token.objects.create(user=user)

    result = create_recipe(
        title="Pancakes",
        description="Sunday",
        image_url="https://example.com/pancakes.jpg",
        calories=450,
        protein=12,
        carbohydrates=55,
        fat=18,
        preparation_minutes=25,
        ingredients=[{"name": "Flour", "quantity": "200 g"}],
        steps=[{"text": "Fry"}],
        ctx=authorization_context(token),
    )

    recipe = Recipe.objects.get(pk=result["id"])
    assert recipe.user == user
    assert result["image_url"] == "https://example.com/pancakes.jpg"
    assert result["calories"] == 450
    assert result["protein"] == 12
    assert result["carbohydrates"] == 55
    assert result["fat"] == 18
    assert result["preparation_minutes"] == 25
    assert result["ingredients"][0]["name"] == "Flour"
    assert result["ingredients"][0]["quantity"] == "200 g"
    assert result["steps"][0]["text"] == "Fry"
    assert Recipe.objects.filter(user=other_user).count() == 0


def test_mcp_recipe_tool_does_not_accept_a_user_argument():
    tool = next(tool for tool in mcp._tool_manager.list_tools() if tool.name == "create_recipe")
    assert set(tool.parameters["properties"]) == {
        "title",
        "description",
        "image_url",
        "calories",
        "protein",
        "carbohydrates",
        "fat",
        "preparation_minutes",
        "ingredients",
        "steps",
    }


@pytest.mark.django_db
def test_mcp_lists_only_the_token_owners_lists_and_recipes(user, other_user):
    token = Token.objects.create(user=user)
    own_list = save_shopping_list(
        user, title="Week", date=date(2026, 11, 2), items=[{"name": "Milk", "quantity": "1 l"}]
    )
    save_recipe(user, title="Pasta", ingredients=[{"name": "Nudeln", "quantity": "500 g"}])
    save_shopping_list(other_user, title="Foreign", date=date(2026, 11, 2))
    save_recipe(other_user, title="Foreign stew")

    lists = list_shopping_lists(ctx=authorization_context(token))
    recipes = list_recipes(ctx=authorization_context(token))

    assert [entry["title"] for entry in lists] == ["Week"]
    assert lists[0]["id"] == own_list.id
    assert lists[0]["items"] == [
        {"id": own_list.items.get().id, "name": "Milk", "quantity": "1 l", "checked": False}
    ]
    assert [entry["title"] for entry in recipes] == ["Pasta"]
    assert recipes[0]["ingredients"] == [{"name": "Nudeln", "quantity": "500 g"}]


@pytest.mark.django_db
def test_mcp_checks_an_item_on_the_owners_list(user, other_user):
    token = Token.objects.create(user=user)
    shopping_list = save_shopping_list(
        user, title="Week", date=date(2026, 11, 2), items=[{"name": "Milk", "quantity": "1 l"}]
    )
    foreign = save_shopping_list(
        other_user, title="Other", date=date(2026, 11, 2), items=[{"name": "Milk", "quantity": "1 l"}]
    )

    result = set_item_checked(name="milk", ctx=authorization_context(token))

    assert result["checked"] is True
    assert result["name"] == "Milk"
    assert shopping_list.items.get().checked is True
    assert foreign.items.get().checked is False


@pytest.mark.django_db
def test_mcp_needs_a_list_when_the_item_name_is_on_two_lists(user):
    token = Token.objects.create(user=user)
    first = save_shopping_list(
        user, title="Today", date=date(2026, 11, 2), items=[{"name": "Milk"}]
    )
    second = save_shopping_list(
        user, title="Weekend", date=date(2026, 11, 3), items=[{"name": "Milk"}]
    )

    with translation.override("en"):
        with pytest.raises(ToolError, match="more than one list"):
            set_item_checked(name="Milk", ctx=authorization_context(token))

    result = set_item_checked(
        name="Milk", list_id=second.id, checked=True, ctx=authorization_context(token)
    )
    assert result["list_id"] == second.id
    assert first.items.get().checked is False
    assert second.items.get().checked is True


@pytest.mark.django_db
def test_mcp_adds_a_recipe_to_todays_list(user, other_user):
    token = Token.objects.create(user=user)
    save_recipe(
        user, title="Pasta", ingredients=[{"name": "Nudeln", "quantity": "500 g"}]
    )
    save_recipe(other_user, title="Pasta", ingredients=[{"name": "Secret"}])

    result = add_recipe_to_list(recipe_title="Pasta", ctx=authorization_context(token))

    shopping_list = ShoppingList.objects.get(pk=result["id"])
    assert shopping_list.user == user
    assert shopping_list.date == timezone.localdate()
    assert [(item["name"], item["quantity"]) for item in result["items"]] == [("Nudeln", "500 g")]
    assert ShoppingItem.objects.filter(shopping_list__user=other_user).count() == 0


@pytest.mark.django_db
def test_mcp_adds_an_item_to_a_named_list(user, other_user):
    token = Token.objects.create(user=user)
    shopping_list = save_shopping_list(user, title="Einkaufen", date=date(2026, 11, 2))
    foreign = save_shopping_list(other_user, title="Einkaufen", date=date(2026, 11, 2))

    result = add_item_to_list(
        name="Bier",
        quantity="6",
        list_title="einkaufen",
        ctx=authorization_context(token),
    )

    assert result["name"] == "Bier"
    assert result["quantity"] == "6"
    assert result["checked"] is False
    assert result["list_id"] == shopping_list.id
    assert list(shopping_list.items.values_list("name", "quantity")) == [("Bier", "6")]
    assert foreign.items.count() == 0


@pytest.mark.django_db
def test_mcp_adds_an_item_to_todays_list(user):
    token = Token.objects.create(user=user)

    result = add_item_to_list(name="Milk", ctx=authorization_context(token))

    shopping_list = ShoppingList.objects.get(pk=result["list_id"])
    assert shopping_list.user == user
    assert shopping_list.date == timezone.localdate()
    assert result["name"] == "Milk"
    assert list(shopping_list.items.values_list("name", flat=True)) == ["Milk"]


@pytest.mark.django_db
def test_mcp_does_not_add_an_item_to_another_users_list(user, other_user):
    token = Token.objects.create(user=user)
    foreign = save_shopping_list(
        other_user, title="Einkaufen", date=date(2026, 11, 2)
    )

    with translation.override("en"):
        with pytest.raises(ToolError, match="Shopping list not found"):
            add_item_to_list(
                name="Bier",
                list_id=foreign.id,
                ctx=authorization_context(token),
            )

    assert foreign.items.count() == 0


def test_mcp_read_and_update_tools_do_not_accept_a_user_argument():
    names = {
        "list_shopping_lists": set(),
        "list_recipes": set(),
        "set_item_checked": {"name", "checked", "list_id"},
        "add_recipe_to_list": {"recipe_id", "recipe_title", "list_id", "list_title"},
        "add_item_to_list": {"name", "quantity", "list_id", "list_title"},
    }
    tools = {tool.name: tool for tool in mcp._tool_manager.list_tools()}
    for name, properties in names.items():
        assert set(tools[name].parameters["properties"]) == properties
