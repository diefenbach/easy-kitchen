import pytest
from asgiref.sync import async_to_sync
from django.urls import reverse
from mcp.server.mcpserver.exceptions import ToolError
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from easy_kitchen import mcp_server as server
from easy_kitchen.models import Article, ShoppingItem, ShoppingList
from easy_kitchen.services import create_item, create_recipe
from easy_kitchen.tests.test_mcp import authorization_context

pytestmark = pytest.mark.django_db


@pytest.fixture(params=["mcp", "api"])
def action(request, user):
    token = Token.objects.create(user=user)
    ctx = authorization_context(token)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    routes = {
        "delete_item": ("shopping-item-detail", "delete", "item_id", "delete_shopping_item"),
        "delete_completed": ("shopping-list-delete-completed", "post", "list_id", "delete_completed_items"),
        "add_item": ("shopping-list-add-item", "post", "list_id", "add_item_to_list"),
        "add_recipe": ("recipe-add-to-list", "post", "recipe_id", "add_recipe_to_list"),
    }

    def call(kind, pk, data=None, expected=200):
        route, method, selector, tool = routes[kind]
        if request.param == "api":
            response = getattr(client, method)(reverse(route, args=[pk]), data or {}, format="json")
            assert response.status_code == expected, response.content
            return response.json() if response.content else None
        kwargs = {"ctx": ctx, selector: pk, **(data or {})}
        if expected >= 400:
            with pytest.raises(ToolError):
                getattr(server, tool)(**kwargs)
            return None
        return getattr(server, tool)(**kwargs)

    return call


def test_deleting_one_item_preserves_other_items_list_and_article(action, shopping_list):
    item = create_item(shopping_list, name="Tofu")
    keep = create_item(shopping_list, name="Rice")
    article = Article.objects.get(user=shopping_list.user, name="Tofu")
    action("delete_item", item.pk, expected=204)
    assert not ShoppingItem.objects.filter(pk=item.pk).exists()
    assert shopping_list.items.get().pk == keep.pk
    assert Article.objects.filter(pk=article.pk).exists()
    assert ShoppingList.objects.filter(pk=shopping_list.pk).exists()
    action("delete_item", item.pk, expected=404)


def test_delete_completed_only_affects_checked_items_on_selected_list(action, shopping_list):
    done = create_item(shopping_list, name="Tofu", checked=True)
    keep = create_item(shopping_list, name="Rice")
    other = ShoppingList.objects.create(user=shopping_list.user, title="Other")
    untouched = create_item(other, name="Salt", checked=True)
    result = action("delete_completed", shopping_list.pk)
    assert result == {"list_id": shopping_list.pk, "deleted_count": 1}
    assert not ShoppingItem.objects.filter(pk=done.pk).exists()
    assert shopping_list.items.get().pk == keep.pk
    assert other.items.get().pk == untouched.pk
    assert action("delete_completed", shopping_list.pk)["deleted_count"] == 0
    assert shopping_list.user.articles.count() == 3


def test_adding_item_merges_quantities_reopens_and_preserves_defaults(action, shopping_list):
    item = create_item(shopping_list, name="Tofu", quantity="400 g", department="dairy", checked=True)
    for amount, total in (("200 g", "600 g"), ("100 g", "700 g")):
        result = action("add_item", shopping_list.pk, {"name": " tofu ", "quantity": amount})
        assert result["id"] == item.pk and result["quantity"] == total
        assert result["checked"] is False and result["department"] == "dairy"
    assert shopping_list.items.count() == 1
    action("add_item", shopping_list.pk, {"name": "Rice", "quantity": "1 kg", "department": "fresh"})
    assert shopping_list.items.get(name="Rice").department_code == "fresh"
    action("add_item", shopping_list.pk, {"name": "Rice", "department": ""})
    assert shopping_list.items.get(name="Rice").department is None
    assert shopping_list.user.articles.get(name="Rice").department is None


def test_null_department_preserves_saved_default_when_adding(action, shopping_list):
    Article.objects.create(user=shopping_list.user, name="Tofu", department=shopping_list.user.departments.get(code="dairy"))
    result = action("add_item", shopping_list.pk, {"name": "Tofu", "department": None})
    assert result["department"] == "dairy"
    assert shopping_list.user.articles.get(name="Tofu").department_code == "dairy"


def test_adding_item_rolls_back_overflow_and_keeps_checked_state(action, shopping_list):
    item = create_item(shopping_list, name="Milk", quantity="1 " + "a" * 98, checked=True, department="dairy")
    action("add_item", shopping_list.pk, {"name": "Milk", "quantity": "1 " + "b" * 98, "department": "fresh"}, expected=400)
    item.refresh_from_db()
    assert item.quantity == "1 " + "a" * 98 and item.checked and item.department_code == "dairy"
    assert shopping_list.user.articles.get(name="Milk").department_code == "dairy"


def test_copy_recipe_merges_ingredients_and_preserves_recipe(action, shopping_list):
    recipe = create_recipe(shopping_list.user, title="Tofu bowl", ingredients=[
        {"name": "Tofu", "quantity": "400 g"}, {"name": "Rice", "quantity": "100 g"},
    ], steps=[{"text": "Cook"}])
    item = create_item(shopping_list, name="Tofu", quantity="200 g")
    for total in ("600 g", "1000 g"):
        result = action("add_recipe", recipe.pk, {"list_id": shopping_list.pk})
        assert result["id"] == shopping_list.pk
        assert next(x for x in result["items"] if x["id"] == item.pk)["quantity"] == total
    assert shopping_list.items.count() == 2
    assert recipe.ingredients.count() == 2 and recipe.steps.get().text == "Cook"


def test_copy_recipe_can_create_a_named_target(action, user):
    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Salt", "quantity": "1 tsp"}])
    result = action("add_recipe", recipe.pk, {"list_title": "Weekend"})
    assert result["title"] == "Weekend"
    assert user.shopping_lists.get().pk == result["id"]
    assert result["items"][0]["name"] == "Salt"


def test_copy_recipe_defaults_to_today(action, user):
    from django.utils import timezone

    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Salt"}])
    result = action("add_recipe", recipe.pk)
    assert user.shopping_lists.get().date == timezone.localdate()
    assert result["items"][0]["name"] == "Salt"


@pytest.mark.parametrize("kind", ["delete_item", "delete_completed", "add_item", "add_recipe"])
def test_actions_reject_foreign_and_missing_sources_without_writes(action, other_user, user, kind):
    foreign_list = ShoppingList.objects.create(user=other_user, title="Private")
    item = create_item(foreign_list, name="Private", checked=True)
    recipe = create_recipe(other_user, title="Private", ingredients=[{"name": "Salt"}])
    pk = item.pk if kind == "delete_item" else recipe.pk if kind == "add_recipe" else foreign_list.pk
    data = {"name": "New"} if kind == "add_item" else {}
    for target in (pk, 999999):
        action(kind, target, data, expected=404)
    assert not user.shopping_lists.exists() and not user.articles.exists()
    assert foreign_list.items.get().pk == item.pk


def test_recipe_copy_rejects_foreign_target_without_writes(action, user, other_user):
    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Salt"}])
    foreign = ShoppingList.objects.create(user=other_user, title="Private")
    for target in (foreign.pk, 999999):
        action("add_recipe", recipe.pk, {"list_id": target}, expected=404)
    assert not foreign.items.exists() and not user.shopping_lists.exists() and not user.articles.exists()


@pytest.mark.parametrize("data", [{"name": " "}, {"name": "Tofu", "quantity": "x" * 101},
                                      {"name": "Tofu", "department": "unknown-department"}])
def test_invalid_add_item_preserves_list_and_defaults(action, shopping_list, data):
    item = create_item(shopping_list, name="Tofu", quantity="400 g", checked=True)
    before = list(shopping_list.user.articles.values())
    action("add_item", shopping_list.pk, data, expected=400)
    item.refresh_from_db()
    assert item.quantity == "400 g" and item.checked
    assert list(shopping_list.user.articles.values()) == before


def test_recipe_copy_rolls_back_new_list_and_earlier_ingredients_on_overflow(action, user):
    recipe = create_recipe(user, title="Overflow", ingredients=[
        {"name": "Salt", "quantity": "1 tsp"},
        {"name": "Milk", "quantity": "1 " + "a" * 98},
        {"name": "Milk", "quantity": "1 " + "b" * 98},
    ])
    action("add_recipe", recipe.pk, {"list_title": "Broken"}, expected=400)
    assert not user.shopping_lists.exists() and not user.articles.exists()


def test_mcp_deletion_annotations_and_authentication():
    tools = {tool.name: tool for tool in server.mcp._tool_manager.list_tools()}
    for name, selector in (("delete_shopping_item", "item_id"), ("delete_completed_items", "list_id")):
        assert set(tools[name].parameters["properties"]) == {selector}
        assert tools[name].annotations.destructive_hint and tools[name].annotations.idempotent_hint
        with pytest.raises(ToolError):
            getattr(server, name)(ctx=authorization_context(Token(key="missing")), **{selector: 1})


@pytest.mark.parametrize("route,method", [("shopping-item-detail", "delete"),
    ("shopping-list-delete-completed", "post"), ("shopping-list-add-item", "post"), ("recipe-add-to-list", "post")])
def test_api_actions_require_authentication(route, method):
    response = getattr(APIClient(), method)(reverse(route, args=[1]), {}, format="json")
    assert response.status_code in (401, 403)


@pytest.mark.django_db(transaction=True)
def test_registered_mcp_delete_completed_returns_count(user):
    shopping_list = ShoppingList.objects.create(user=user, title="Shop")
    create_item(shopping_list, name="Tofu", checked=True)
    ctx = authorization_context(Token.objects.create(user=user))
    result = async_to_sync(server.mcp._tool_manager.call_tool)(
        "delete_completed_items", {"list_id": shopping_list.pk}, ctx,
    )
    assert result == {"list_id": shopping_list.pk, "deleted_count": 1}
