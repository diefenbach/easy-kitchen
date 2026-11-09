import json

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

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(params=["api", "mcp"])
def query(request, user):
    token = Token.objects.create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    ctx = authorization_context(token)

    def call(kind, params=None, *, expected=200):
        if request.param == "api":
            route = {"recipes": "recipe-list", "shopping_lists": "shopping-list-list",
                     "shopping_items": "shopping-item-list", "articles": "article-list",
                     "departments": "department-list"}[kind]
            response = client.get(reverse(route), params or {})
            assert response.status_code == expected, response.content
            return response.json()
        if expected != 200:
            with pytest.raises(ToolError):
                async_to_sync(server.mcp._tool_manager.call_tool)(f"list_{kind}", params or {}, ctx)
            return None
        return async_to_sync(server.mcp._tool_manager.call_tool)(f"list_{kind}", params or {}, ctx)

    return call


def test_recipe_search_filters_and_summary_are_owned(query, user, other_user):
    recipe = create_recipe(user, title="Dinner", description="Korean inspired",
                           ingredients=[{"name": "Tofu"}], steps=["Cook"])
    recipe.is_favorite = True
    recipe.save()
    create_recipe(user, title="Another tofu dinner")
    create_recipe(other_user, title="Korean tofu", ingredients=[{"name": "Tofu"}])
    result = query("recipes", {"q": "Korean tofu", "is_favorite": True, "summary": True})
    assert [row["id"] for row in result] == [recipe.pk]
    assert "ingredients" not in result[0] and "steps" not in result[0]
    assert result[0]["is_favorite"] is True
    full = query("recipes", {"q": "Korean tofu"})[0]
    assert full["ingredients"][0]["name"] == "Tofu" and full["steps"][0]["text"] == "Cook"


def test_pagination_is_bounded_and_stable(query, user, other_user):
    records = [create_recipe(user, title=f"Soup {index}") for index in range(55)]
    create_recipe(other_user, title="Private")
    expected_ids = [record.pk for record in reversed(records)]
    assert [row["id"] for row in query("recipes")] == expected_ids[:50]
    assert [row["id"] for row in query("recipes", {"limit": 3, "offset": 2})] == expected_ids[2:5]
    assert query("recipes", {"offset": 55}) == []


def test_list_dates_search_and_summary(query, user, other_user):
    own = ShoppingList.objects.create(user=user, title="Weekend", date="2027-01-03")
    create_item(own, name="Tofu")
    ShoppingList.objects.create(user=user, title="Weekend old", date="2026-12-01")
    ShoppingList.objects.create(user=other_user, title="Weekend private", date="2027-01-03")
    result = query("shopping_lists", {"q": "weekend", "date_from": "2027-01-01",
                                      "date_to": "2027-01-03", "summary": True})
    assert [row["id"] for row in result] == [own.pk]
    assert "items" not in result[0]
    assert query("shopping_lists", {"q": "weekend", "date_from": "2027-01-01"})[0]["items"][0]["name"] == "Tofu"


def test_item_filters_and_article_departments(query, user, other_user):
    own = ShoppingList.objects.create(user=user, title="Shop")
    item = create_item(own, name="Tofu", checked=False, department="dairy")
    create_item(own, name="Rice", checked=True, department="fresh")
    other = ShoppingList.objects.create(user=other_user, title="Private")
    create_item(other, name="Tofu", department="dairy")
    result = query("shopping_items", {"q": "tofu", "checked": False, "list_id": own.pk})
    assert [row["id"] for row in result] == [item.pk]
    query("shopping_items", {"list_id": other.pk}, expected=404)
    result = query("articles", {"q": "tofu", "department": "dairy"})
    assert [row["name"] for row in result] == ["Tofu"]
    assert query("articles", {"department": ""}) == []


def test_department_search_and_window(query, user):
    rows = query("departments", {"q": "dairy"})
    assert len(rows) == 1 and rows[0]["code"] == "dairy"
    assert len(query("departments", {"limit": 2})) == 2


def test_omitted_boolean_filters_include_both_states(query, user):
    first = create_recipe(user, title="Favorite")
    first.is_favorite = True
    first.save()
    second = create_recipe(user, title="Ordinary")
    assert {row["id"] for row in query("recipes")} == {first.pk, second.pk}
    assert [row["id"] for row in query("recipes", {"is_favorite": False})] == [second.pk]
    shopping_list = ShoppingList.objects.create(user=user, title="Shop")
    done = create_item(shopping_list, name="Tofu", checked=True)
    open_item = create_item(shopping_list, name="Rice")
    assert {row["id"] for row in query("shopping_items")} == {done.pk, open_item.pk}


def test_compact_recipe_and_list_reads_do_not_load_children(user, django_assert_num_queries):
    from easy_kitchen.presenters import recipe_data, shopping_list_data
    from easy_kitchen.services import query_owned_recipes, query_owned_shopping_lists

    create_recipe(user, title="Tofu", ingredients=[{"name": "Tofu"}, {"name": "Tofu extra"}], steps=["Cook"])
    shopping_list = ShoppingList.objects.create(user=user, title="Shop")
    create_item(shopping_list, name="Tofu")
    with django_assert_num_queries(1):
        recipes = [recipe_data(row, summary=True) for row in query_owned_recipes(user, q="tofu", summary=True)]
    assert len(recipes) == 1 and "ingredients" not in recipes[0]
    with django_assert_num_queries(1):
        lists = [shopping_list_data(row, summary=True) for row in query_owned_shopping_lists(user, summary=True)]
    assert len(lists) == 1 and "items" not in lists[0]


def test_matching_ids_and_normalized_names_are_accepted(user):
    recipe = create_recipe(user, title="Tofu Soup")
    shopping_list = ShoppingList.objects.create(user=user, title="Weekend Shop")
    item = create_item(shopping_list, name="Firm Tofu")
    ctx = authorization_context(Token.objects.create(user=user))
    assert server.update_recipe(ctx=ctx, recipe_id=recipe.pk, recipe_title=" tofu   soup ", changes={"fat": 10})["fat"] == 10
    assert server.add_recipe_to_list(ctx=ctx, recipe_id=recipe.pk, list_id=shopping_list.pk,
                                      list_title=" WEEKEND   shop ")["id"] == shopping_list.pk
    with pytest.raises(ToolError) as error:
        server.set_item_checked(ctx=ctx, item_id=item.pk, name="Different")
    assert json.loads(str(error.value))["code"] == "selection_mismatch"
    assert server.set_item_checked(ctx=ctx, item_id=item.pk, name=" firm  tofu ")["checked"] is True


def test_collection_query_parameters_match_registered_mcp_tools():
    response = APIClient().get(reverse("api-schema"), HTTP_ACCEPT="application/json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    tools = {tool.name: tool for tool in server.mcp._tool_manager.list_tools()}
    collections = {"recipes": "list_recipes", "shopping-lists": "list_shopping_lists",
                   "shopping-items": "list_shopping_items", "articles": "list_articles",
                   "departments": "list_departments"}
    for resource, name in collections.items():
        parameters = {field["name"]: field["schema"]
                      for field in paths[f"/api/v1/{resource}/"]["get"]["parameters"]}
        properties = tools[name].parameters["properties"]
        assert set(parameters) == set(properties)
        assert parameters["limit"]["default"] == properties["limit"]["default"] == 50
        assert parameters["limit"]["maximum"] == properties["limit"]["maximum"] == 200


@pytest.mark.parametrize("kind,params", [
    ("recipes", {"limit": 0}), ("recipes", {"limit": 201}),
    ("recipes", {"offset": -1}), ("recipes", {"q": "x" * 256}),
    ("recipes", {"is_favorite": "wrong"}), ("shopping_lists", {"summary": "wrong"}),
    ("shopping_lists", {"date_from": "2027-02-01", "date_to": "2027-01-01"}),
    ("shopping_items", {"checked": "wrong"}), ("articles", {"department": "unknown"}),
    ("departments", {"unknown": True}),
])
def test_invalid_queries_are_rejected(query, kind, params):
    query(kind, params, expected=400)


@pytest.mark.parametrize("operation", ["update_recipe", "set_recipe_favorite", "set_meal_plan_recipe", "add_recipe_to_list"])
def test_conflicting_recipe_selectors_fail_without_writes(user, operation):
    recipe = create_recipe(user, title="Soup")
    ctx = authorization_context(Token.objects.create(user=user))
    kwargs = {"recipe_id": recipe.pk, "recipe_title": "Different", "ctx": ctx}
    kwargs.update({"changes": {"fat": 10}} if operation == "update_recipe" else
                  {"is_favorite": True} if operation == "set_recipe_favorite" else
                  {"date": "2027-01-01"} if operation == "set_meal_plan_recipe" else {})
    with pytest.raises(ToolError) as error:
        getattr(server, operation)(**kwargs)
    assert json.loads(str(error.value))["code"] == "selection_mismatch"
    recipe.refresh_from_db()
    assert recipe.fat is None and not recipe.is_favorite
    assert not user.shopping_lists.exists() and not user.meal_plan_entries.exists()


def test_conflicting_target_title_fails_in_api_and_mcp(user):
    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Salt"}])
    shopping_list = ShoppingList.objects.create(user=user, title="Weekend")
    token = Token.objects.create(user=user)
    ctx = authorization_context(token)
    with pytest.raises(ToolError) as error:
        server.add_recipe_to_list(ctx=ctx, recipe_id=recipe.pk, list_id=shopping_list.pk, list_title="Different")
    assert json.loads(str(error.value))["code"] == "selection_mismatch"
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    response = client.post(reverse("recipe-add-to-list", args=[recipe.pk]),
                           {"list_id": shopping_list.pk, "list_title": "Different"}, format="json")
    assert response.status_code == 400 and response.json()["code"] == "selection_mismatch"
    assert not shopping_list.items.exists()


@pytest.mark.parametrize("path", ["checked_tool", "item_tool", "api"])
def test_checked_only_updates_have_no_article_side_effects(user, path):
    shopping_list = ShoppingList.objects.create(user=user, title="Shop")
    item = create_item(shopping_list, name="Tofu", quantity="400 g", department="dairy")
    Article.objects.filter(user=user).delete()
    token = Token.objects.create(user=user)
    ctx = authorization_context(token)
    if path == "checked_tool":
        server.set_item_checked(ctx=ctx, item_id=item.pk, checked=True)
    elif path == "item_tool":
        server.update_shopping_item(ctx=ctx, item_id=item.pk, changes={"checked": True})
    else:
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        assert client.patch(reverse("shopping-item-detail", args=[item.pk]), {"checked": True}, format="json").status_code == 200
    item.refresh_from_db()
    assert item.checked and item.quantity == "400 g" and item.department_code == "dairy"
    assert not user.articles.exists()
