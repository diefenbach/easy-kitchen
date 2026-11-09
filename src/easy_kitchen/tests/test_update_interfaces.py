from datetime import date

import pytest
from asgiref.sync import async_to_sync
from django.urls import reverse
from mcp.server.mcpserver.exceptions import ToolError
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from easy_kitchen import mcp_server as server
from easy_kitchen.models import Article, ShoppingList
from easy_kitchen.services import create_item, create_recipe
from easy_kitchen.tests.test_mcp import authorization_context

pytestmark = pytest.mark.django_db


@pytest.fixture(params=["mcp", "api"])
def update(request, user):
    token = Token.objects.create(user=user)
    ctx = authorization_context(token)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    names = {
        "shopping_item": ("shopping-item-detail", "item_id"),
        "shopping_list": ("shopping-list-detail", "list_id"),
        "article": ("article-detail", "article_id"),
        "department": ("department-detail", "department_id"),
        "favorite": ("recipe-favorite", "recipe_id"),
    }

    def call(kind, pk, changes, expected=200):
        route, selector = names[kind]
        if request.param == "api":
            method = client.post if kind == "favorite" else client.patch
            response = method(reverse(route, args=[pk]), changes, format="json")
            assert response.status_code == expected, response.content
            return response.json()
        tool = server.set_recipe_favorite if kind == "favorite" else getattr(server, f"update_{kind}")
        kwargs = {selector: pk, "ctx": ctx}
        kwargs.update(changes if kind == "favorite" else {"changes": changes})
        if expected != 200:
            with pytest.raises(ToolError):
                tool(**kwargs)
            return None
        return tool(**kwargs)

    return call


def test_item_update_replaces_quantity_preserves_state_and_updates_default(update, shopping_list):
    item = create_item(shopping_list, name="Tofu", quantity="400 g", department="dairy")
    item.checked = True
    item.save()
    position = item.position
    for _ in range(2):
        result = update("shopping_item", item.pk, {"quantity": "600 g"})
        assert result["quantity"] == "600 g"
    item.refresh_from_db()
    assert item.name == "Tofu" and item.checked and item.position == position
    assert item.department_code == "dairy"
    update("shopping_item", item.pk, {"name": "Smoked tofu", "department": "fresh"})
    item.refresh_from_db()
    assert item.name == "Smoked tofu" and item.department_code == "fresh"
    assert Article.objects.get(user=shopping_list.user, name="Smoked tofu").department_code == "fresh"
    update("shopping_item", item.pk, {"quantity": "", "department": ""})
    item.refresh_from_db()
    assert item.quantity == item.department_code == ""


def test_list_update_preserves_items_and_omitted_metadata(update, shopping_list):
    item = create_item(shopping_list, name="Tofu")
    original_date = shopping_list.date
    position = shopping_list.position
    update("shopping_list", shopping_list.pk, {"title": "Weekend"})
    shopping_list.refresh_from_db()
    assert shopping_list.title == "Weekend" and shopping_list.date == original_date
    result = update("shopping_list", shopping_list.pk, {"date": "2027-01-02", "icon": "cart"})
    shopping_list.refresh_from_db()
    assert shopping_list.date == date(2027, 1, 2) and shopping_list.icon == "cart"
    assert shopping_list.position == position and shopping_list.items.get().pk == item.pk
    assert result["title"] == "Weekend"


def test_article_update_preserves_list_entries_and_omitted_default(update, shopping_list):
    item = create_item(shopping_list, name="Tofu", department="dairy")
    article = shopping_list.user.articles.get(name="Tofu")
    update("article", article.pk, {"name": "Firm tofu"})
    article.refresh_from_db()
    assert article.name == "Firm tofu" and article.department_code == "dairy"
    update("article", article.pk, {"department": "fresh"})
    article.refresh_from_db()
    item.refresh_from_db()
    assert article.department_code == "fresh"
    assert item.name == "Tofu" and item.department_code == "dairy"
    update("article", article.pk, {"department": ""})
    article.refresh_from_db()
    assert article.department is None


def test_department_rename_preserves_code_position_and_references(update, shopping_list):
    item = create_item(shopping_list, name="Tofu", department="dairy")
    department = item.department
    code, position = department.code, department.position
    for _ in range(2):
        result = update("department", department.pk, {"name": "Chilled food"})
        assert result["code"] == code
    department.refresh_from_db()
    item.refresh_from_db()
    assert department.name == "Chilled food" and department.position == position
    assert item.department_id == department.pk
    assert shopping_list.user.articles.get(name="Tofu").department_id == department.pk


def test_favorite_is_explicit_and_idempotent(update, user):
    recipe = create_recipe(user, title="Tofu", calories=1250, steps=[{"text": "Fry"}])
    step_pk = recipe.steps.get().pk
    for value in (True, True, False, False):
        result = update("favorite", recipe.pk, {"is_favorite": value})
        recipe.refresh_from_db()
        assert recipe.is_favorite is value and result["is_favorite"] is value
        assert recipe.calories == 1250 and recipe.steps.get().pk == step_pk


@pytest.mark.parametrize("kind", ["shopping_item", "shopping_list", "article", "department", "favorite"])
def test_update_rejects_foreign_and_missing_objects(update, other_user, kind):
    foreign_list = ShoppingList.objects.create(user=other_user, title="Private")
    item = create_item(foreign_list, name="Private", quantity="1", department="dairy")
    foreign = {
        "shopping_item": item, "shopping_list": foreign_list,
        "article": other_user.articles.get(name="Private"), "department": item.department,
        "favorite": create_recipe(other_user, title="Private"),
    }[kind]
    changes = {"is_favorite": True} if kind == "favorite" else {"name": "Changed"}
    if kind == "shopping_list":
        changes = {"title": "Changed"}
    for pk in (foreign.pk, 999999):
        update(kind, pk, changes, expected=404)
    foreign.refresh_from_db()
    if kind == "favorite":
        assert not foreign.is_favorite
    elif kind == "shopping_list":
        assert foreign.title == "Private"
    else:
        assert foreign.name != "Changed"


@pytest.mark.parametrize("kind,changes", [
    ("shopping_item", {"name": ""}), ("shopping_item", {"quantity": "x" * 101}),
    ("shopping_item", {"name": "Changed", "department": "not-a-department"}),
    ("shopping_list", {"title": ""}), ("shopping_list", {"icon": "invalid"}),
    ("shopping_list", {"date": "2027-02-30"}),
    ("article", {"name": ""}), ("article", {"department": "not-a-department"}),
    ("department", {"name": ""}), ("department", {"name": "x" * 101}),
    ("department", {"code": "changed"}), ("favorite", {"is_favorite": "invalid"}),
])
def test_invalid_updates_leave_objects_unchanged(update, shopping_list, kind, changes):
    item = create_item(shopping_list, name="Tofu", department="dairy")
    obj = {
        "shopping_item": item, "shopping_list": shopping_list,
        "article": shopping_list.user.articles.get(name="Tofu"), "department": item.department,
        "favorite": create_recipe(shopping_list.user, title="Tofu"),
    }[kind]
    before = obj.__dict__.copy()
    update(kind, obj.pk, changes, expected=400)
    obj.refresh_from_db()
    for field in obj._meta.concrete_fields:
        assert getattr(obj, field.attname) == before[field.attname]


@pytest.mark.parametrize("kind", ["article", "department"])
def test_duplicate_names_are_rejected(update, shopping_list, kind):
    item = create_item(shopping_list, name="Tofu", department="dairy")
    if kind == "article":
        obj = shopping_list.user.articles.get(name="Tofu")
        duplicate = Article.objects.create(user=shopping_list.user, name="Other")
    else:
        obj = item.department
        duplicate = shopping_list.user.departments.get(code="fresh")
    update(kind, obj.pk, {"name": duplicate.name.swapcase()}, expected=400)


def test_articles_are_discoverable_only_by_the_owner(user, other_user):
    own = Article.objects.create(user=user, name="Tofu")
    Article.objects.create(user=other_user, name="Private")
    token = Token.objects.create(user=user)
    result = server.list_articles(authorization_context(token))
    assert [article["id"] for article in result] == [own.pk]
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    result = client.get(reverse("article-list"))
    assert result.status_code == 200
    assert [article["id"] for article in result.json()] == [own.pk]


def test_mcp_update_schemas_and_authentication():
    selectors = {"shopping_item": "item_id", "shopping_list": "list_id", "article": "article_id", "department": "department_id"}
    tools = {tool.name: tool for tool in server.mcp._tool_manager.list_tools()}
    for kind, selector in selectors.items():
        name = f"update_{kind}"
        assert set(tools[name].parameters["properties"]) == {selector, "changes"}
        assert tools[name].annotations.idempotent_hint
        with pytest.raises(ToolError):
            getattr(server, name)(ctx=authorization_context(Token(key="missing")), **{selector: 1}, changes={})


@pytest.mark.parametrize("route,method,body", [
    ("shopping-item-detail", "patch", {"quantity": "1"}),
    ("shopping-list-detail", "patch", {"title": "Changed"}),
    ("article-detail", "patch", {"name": "Changed"}),
    ("department-detail", "patch", {"name": "Changed"}),
    ("recipe-favorite", "post", {"is_favorite": True}),
])
def test_api_updates_require_authentication(route, method, body):
    response = getattr(APIClient(), method)(reverse(route, args=[1]), body, format="json")
    assert response.status_code in (401, 403)


@pytest.mark.parametrize("kind", ["shopping_item", "shopping_list", "article", "department"])
def test_empty_update_preserves_values(update, shopping_list, kind):
    item = create_item(shopping_list, name="Tofu", department="dairy")
    obj = {"shopping_item": item, "shopping_list": shopping_list,
           "article": shopping_list.user.articles.get(name="Tofu"), "department": item.department}[kind]
    before = obj.__dict__.copy()
    update(kind, obj.pk, {})
    obj.refresh_from_db()
    for field in obj._meta.concrete_fields:
        assert getattr(obj, field.attname) == before[field.attname]


def test_mcp_favorite_selects_by_title_and_requires_authentication(user):
    recipe = create_recipe(user, title="Tofu")
    ctx = authorization_context(Token.objects.create(user=user))
    assert server.set_recipe_favorite(ctx=ctx, recipe_title=" tofu ", is_favorite=True)["id"] == recipe.pk
    with pytest.raises(ToolError):
        server.set_recipe_favorite(ctx=authorization_context(Token(key="missing")), recipe_id=recipe.pk, is_favorite=True)
    with pytest.raises(ToolError):
        server.list_articles(authorization_context(Token(key="missing")))


@pytest.mark.parametrize("route", ["shopping-item-detail", "article-detail", "department-detail"])
@pytest.mark.parametrize("body", [[], [{"name": "Changed"}], 123])
def test_api_update_rejects_non_object_body(user, shopping_list, route, body):
    item = create_item(shopping_list, name="Tofu", department="dairy")
    pk = {"shopping-item-detail": item.pk, "article-detail": user.articles.get(name="Tofu").pk,
          "department-detail": item.department_id}[route]
    client = APIClient()
    client.force_authenticate(user)
    response = client.patch(reverse(route, args=[pk]), body, format="json")
    assert response.status_code == 400


@pytest.mark.django_db(transaction=True)
def test_registered_mcp_update_parses_date(user):
    ctx = authorization_context(Token.objects.create(user=user))
    shopping_list = ShoppingList.objects.create(user=user, title="Shop")
    result = async_to_sync(server.mcp._tool_manager.call_tool)(
        "update_shopping_list", {"list_id": shopping_list.pk, "changes": {"date": "2027-01-02"}}, ctx,
    )
    assert result["date"] == "2027-01-02"
