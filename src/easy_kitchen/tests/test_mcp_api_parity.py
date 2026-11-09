import pytest
from asgiref.sync import async_to_sync
from django.urls import reverse
from mcp.server.mcpserver.exceptions import ToolError
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from easy_kitchen import mcp_server as server
from easy_kitchen.api.urls import router
from easy_kitchen.models import MealPlanEntry, Recipe, ShoppingList
from easy_kitchen.presenters import item_data
from easy_kitchen.services import create_item, create_recipe
from easy_kitchen.tests.test_mcp import authorization_context

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(params=["api", "mcp"])
def call(request, user):
    token = Token.objects.create(user=user)
    ctx = authorization_context(token)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def invoke(tool, route, *, pk=None, method="get", data=None, status=200):
        if request.param == "api":
            url = reverse(route, args=[pk] if pk is not None else [])
            body = {key: value for key, value in (data or {}).items()
                    if pk is None or key not in {"recipe_id", "list_id", "item_id", "article_id", "department_id"}}
            response = getattr(client, method)(url, body, format="json")
            assert response.status_code == status, response.content
            return response.json() if response.content else None
        arguments = {"list_id": pk, "changes": data} if tool == "update_shopping_list" else data or {}
        if status >= 400:
            with pytest.raises(ToolError):
                async_to_sync(server.mcp._tool_manager.call_tool)(tool, arguments, ctx)
            return None
        return async_to_sync(server.mcp._tool_manager.call_tool)(tool, arguments, ctx)

    return invoke


@pytest.mark.parametrize("kind", ["recipe", "shopping_list", "shopping_item", "article", "department"])
def test_single_record_reads_are_owned_and_match_public_data(call, user, other_user, kind):
    own_list = ShoppingList.objects.create(user=user, title="Shop")
    item = create_item(own_list, name="Tofu", department="dairy")
    own = {"recipe": create_recipe(user, title="Tofu", ingredients=[{"name": "Salt"}], steps=["Cook"]),
           "shopping_list": own_list, "shopping_item": item,
           "article": user.articles.get(name="Tofu"), "department": item.department}[kind]
    foreign_list = ShoppingList.objects.create(user=other_user, title="Private")
    foreign_item = create_item(foreign_list, name="Private", department="dairy")
    foreign = {"recipe": create_recipe(other_user, title="Private"), "shopping_list": foreign_list,
               "shopping_item": foreign_item, "article": other_user.articles.get(name="Private"),
               "department": foreign_item.department}[kind]
    selector = {"shopping_list": "list_id", "shopping_item": "item_id"}.get(kind, f"{kind}_id")
    route = f"{kind.replace('_', '-')}-detail"
    result = call(f"get_{kind}", route, pk=own.pk, data={selector: own.pk})
    assert result["id"] == own.pk
    for pk in (foreign.pk, 999999):
        call(f"get_{kind}", route, pk=pk, data={selector: pk}, status=404)


def test_item_collection_never_includes_another_users_items(call, user, other_user):
    own_list = ShoppingList.objects.create(user=user, title="Shop")
    item = create_item(own_list, name="Tofu")
    create_item(ShoppingList.objects.create(user=other_user, title="Private"), name="Private")
    result = call("list_shopping_items", "shopping-item-list")
    assert [line["id"] for line in result] == [item.pk]
    assert result[0] == item_data(item)


@pytest.mark.parametrize("kind", ["recipe", "shopping_list"])
def test_delete_root_removes_owned_children_but_preserves_other_records(call, user, other_user, kind):
    shopping_list = ShoppingList.objects.create(user=user, title="Shop")
    item = create_item(shopping_list, name="Tofu")
    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Salt"}], steps=["Cook"])
    MealPlanEntry.objects.create(user=user, date="2027-01-01", recipe=recipe)
    foreign = (create_recipe(other_user, title="Private") if kind == "recipe" else
               ShoppingList.objects.create(user=other_user, title="Private"))
    obj = recipe if kind == "recipe" else shopping_list
    selector = "recipe_id" if kind == "recipe" else "list_id"
    route = f"{kind.replace('_', '-')}-detail"
    call(f"delete_{kind}", route, pk=foreign.pk, method="delete", data={selector: foreign.pk}, status=404)
    call(f"delete_{kind}", route, pk=obj.pk, method="delete", data={selector: obj.pk}, status=204)
    assert not type(obj).objects.filter(pk=obj.pk).exists()
    assert type(foreign).objects.filter(pk=foreign.pk).exists()
    assert user.articles.get(name="Tofu")
    if kind == "recipe":
        assert not recipe.ingredients.exists() and not recipe.steps.exists()
        assert not user.meal_plan_entries.exists()
        assert shopping_list.items.get().pk == item.pk
    else:
        assert not shopping_list.items.exists() and Recipe.objects.filter(pk=recipe.pk).exists()
    call(f"delete_{kind}", route, pk=obj.pk, method="delete", data={selector: obj.pk}, status=404)


SORTS = {
    "shopping_lists": ("shopping-list-reorder-lists", "list_ids"),
    "shopping_items": ("shopping-list-reorder", "item_ids"),
    "recipes": ("recipe-reorder-recipes", "recipe_ids"),
    "recipe_ingredients": ("recipe-reorder-ingredients", "line_ids"),
    "recipe_steps": ("recipe-reorder-steps", "line_ids"),
}


@pytest.mark.parametrize("kind", list(SORTS))
@pytest.mark.parametrize("invalid", [False, True])
def test_reordering_is_complete_owned_and_persistent(call, user, other_user, kind, invalid):
    shopping_list = ShoppingList.objects.create(user=user, title="Shop")
    other_list = ShoppingList.objects.create(user=other_user, title="Private")
    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Salt"}, {"name": "Water"}], steps=["Boil", "Serve"])
    private = create_recipe(other_user, title="Private", ingredients=[{"name": "Private"}], steps=["Private"])
    if kind == "shopping_lists":
        records = [shopping_list, ShoppingList.objects.create(user=user, title="Second")]
        manager, foreign, parent, selection = user.shopping_lists, other_list.pk, None, {}
    elif kind == "recipes":
        records = [recipe, create_recipe(user, title="Second")]
        manager, foreign, parent, selection = user.recipes, private.pk, None, {}
    elif kind == "shopping_items":
        records = [create_item(shopping_list, name="Tofu"), create_item(shopping_list, name="Rice")]
        manager, foreign, parent = shopping_list.items, create_item(other_list, name="Private").pk, shopping_list.pk
        selection = {"list_id": parent}
    else:
        field = "ingredients" if kind.endswith("ingredients") else "steps"
        manager = getattr(recipe, field)
        records, foreign, parent = list(manager.all()), getattr(private, field).get().pk, recipe.pk
        selection = {"recipe_id": parent}
    route, field = SORTS[kind]
    before = list(manager.values_list("pk", "position"))
    ids = [record.pk for record in reversed(records)]
    if invalid:
        for bad in ([ids[0]], [ids[0], ids[0]], [ids[0], foreign], [ids[0], 999999]):
            call(f"reorder_{kind}", route, pk=parent, method="post", data={**selection, field: bad}, status=400)
            assert list(manager.values_list("pk", "position")) == before
        return
    result = call(f"reorder_{kind}", route, pk=parent, method="post", data={**selection, field: ids})
    assert list(manager.values_list("pk", flat=True)) == ids
    assert list(manager.values_list("position", flat=True)) == [1, 2]
    assert result


@pytest.mark.parametrize("kind", ["recipes", "shopping_lists"])
def test_batch_import_preserves_input_order_and_shifts_existing_records(call, user, other_user, kind):
    existing = create_recipe(user, title="Existing") if kind == "recipes" else ShoppingList.objects.create(user=user, title="Existing")
    records = ([{"title": "First", "ingredients": [{"name": "Tofu", "quantity": "400 g", "position": 2}], "steps": [{"text": "Cook", "position": 1}]}, {"title": "Second"}]
               if kind == "recipes" else [{"title": "First", "items": [{"name": "Tofu", "quantity": "400 g", "department": "dairy", "checked": True}]}, {"title": "Second", "icon": "cart"}])
    route = "recipe-import-json" if kind == "recipes" else "shopping-list-import-json"
    key = "recipes" if kind == "recipes" else "lists"
    result = call(f"import_{kind}", route, method="post", data={key: records}, status=201)
    assert [record["title"] for record in result] == ["First", "Second"]
    manager = user.recipes if kind == "recipes" else user.shopping_lists
    assert list(manager.values_list("title", flat=True)) == ["First", "Second", "Existing"]
    existing.refresh_from_db()
    assert existing.position == 3
    foreign = other_user.recipes if kind == "recipes" else other_user.shopping_lists
    assert not foreign.exists()


@pytest.mark.parametrize("kind", ["recipes", "shopping_lists"])
def test_import_rejects_invalid_later_records_without_partial_writes(call, user, kind):
    records = [{"title": "Valid"}, {"title": "   "}]
    key, route = ("recipes", "recipe-import-json") if kind == "recipes" else ("lists", "shopping-list-import-json")
    call(f"import_{kind}", route, method="post", data={key: records}, status=400)
    assert not user.recipes.exists() and not user.shopping_lists.exists() and not user.articles.exists()


@pytest.mark.parametrize("kind", ["recipes", "shopping_lists"])
def test_import_cannot_assign_records_to_a_different_user(call, user, other_user, kind):
    key, route = ("recipes", "recipe-import-json") if kind == "recipes" else ("lists", "shopping-list-import-json")
    call(f"import_{kind}", route, method="post", data={key: [{"title": "Injected", "user": other_user.pk}]}, status=400)
    assert not user.recipes.exists() and not other_user.recipes.exists()
    assert not user.shopping_lists.exists() and not other_user.shopping_lists.exists()


@pytest.mark.parametrize("kind", ["recipes", "shopping_lists"])
def test_import_rejects_positions_that_do_not_fit_the_database(call, user, kind):
    key, route = ("recipes", "recipe-import-json") if kind == "recipes" else ("lists", "shopping-list-import-json")
    children = "ingredients" if kind == "recipes" else "items"
    records = [{"title": "Valid"}, {"title": "Invalid", children: [{"name": "Tofu", "position": 2147483648}]}]
    call(f"import_{kind}", route, method="post", data={key: records}, status=400)
    assert not user.recipes.exists() and not user.shopping_lists.exists() and not user.articles.exists()


@pytest.mark.parametrize("kind", ["shopping_items", "recipe_ingredients", "recipe_steps"])
def test_reordering_rejects_foreign_parent_ids(call, user, other_user, kind):
    if kind == "shopping_items":
        parent = ShoppingList.objects.create(user=other_user, title="Private")
        line = create_item(parent, name="Private")
        manager, selector = parent.items, "list_id"
    else:
        parent = create_recipe(other_user, title="Private", ingredients=[{"name": "Salt"}], steps=["Cook"])
        manager = parent.ingredients if kind.endswith("ingredients") else parent.steps
        line, selector = manager.get(), "recipe_id"
    route, field = SORTS[kind]
    before = list(manager.values())
    for pk in (parent.pk, 999999):
        call(f"reorder_{kind}", route, pk=pk, method="post", data={selector: pk, field: [line.pk]}, status=404)
    assert list(manager.values()) == before


@pytest.mark.parametrize("kind", ["recipes", "shopping_lists"])
def test_import_rolls_back_existing_positions_and_defaults_on_business_error(call, user, kind):
    if kind == "recipes":
        existing = create_recipe(user, title="Existing")
        records = [{"title": "First"}, {"title": "Bad", "image_url": "https://"}]
        key, route = "recipes", "recipe-import-json"
    else:
        existing = ShoppingList.objects.create(user=user, title="Existing")
        records = [{"title": "First", "items": [{"name": "Tofu"}]},
                   {"title": "Bad", "items": [{"name": "Rice", "department": "unknown-department"}]}]
        key, route = "lists", "shopping-list-import-json"
    call(f"import_{kind}", route, method="post", data={key: records}, status=400)
    existing.refresh_from_db()
    assert existing.position == 1
    manager = user.recipes if kind == "recipes" else user.shopping_lists
    assert list(manager.values_list("pk", flat=True)) == [existing.pk]
    assert not user.articles.exists()


def test_list_update_can_replace_and_clear_items_in_both_interfaces(call, user):
    shopping_list = ShoppingList.objects.create(user=user, title="Shop")
    create_item(shopping_list, name="Old")
    data = {"items": [{"name": "Tofu", "quantity": "400 g", "checked": True, "department": "dairy"}]}
    result = call("update_shopping_list", "shopping-list-detail", pk=shopping_list.pk, method="patch", data=data)
    assert result["title"] == "Shop" and len(result["items"]) == 1
    item = shopping_list.items.get()
    assert item.name == "Tofu" and item.quantity == "400 g" and item.checked and item.department_code == "dairy"
    call("update_shopping_list", "shopping-list-detail", pk=shopping_list.pk, method="patch",
         data={"items": [{"name": " "}]}, status=400)
    assert shopping_list.items.get().pk == item.pk
    result = call("update_shopping_list", "shopping-list-detail", pk=shopping_list.pk, method="patch", data={"items": []})
    assert result["items"] == [] and not shopping_list.items.exists()


def test_new_tools_have_authentication_and_appropriate_annotations():
    arguments = {
        "get_recipe": {"recipe_id": 1}, "get_shopping_list": {"list_id": 1},
        "get_shopping_item": {"item_id": 1}, "get_article": {"article_id": 1},
        "get_department": {"department_id": 1}, "list_shopping_items": {},
        "delete_recipe": {"recipe_id": 1}, "delete_shopping_list": {"list_id": 1},
        "reorder_shopping_lists": {"list_ids": []}, "reorder_recipes": {"recipe_ids": []},
        "reorder_shopping_items": {"list_id": 1, "item_ids": []},
        "reorder_recipe_ingredients": {"recipe_id": 1, "line_ids": []},
        "reorder_recipe_steps": {"recipe_id": 1, "line_ids": []},
        "import_recipes": {"recipes": []}, "import_shopping_lists": {"lists": []},
    }
    tools = {tool.name: tool for tool in server.mcp._tool_manager.list_tools()}
    ctx = authorization_context(Token(key="missing"))
    for name, data in arguments.items():
        tool = tools[name]
        assert "user" not in tool.parameters["properties"]
        read_only = name.startswith("get_") or name.startswith("list_")
        assert tool.annotations.read_only_hint == read_only
        assert tool.annotations.idempotent_hint == (not name.startswith("import_"))
        assert tool.annotations.destructive_hint == (name.startswith("delete_") or name.startswith("reorder_"))
        with pytest.raises(ToolError):
            async_to_sync(server.mcp._tool_manager.call_tool)(name, data, ctx)


def test_every_rest_business_action_has_a_registered_mcp_equivalent():
    expected = {
        "DepartmentViewSet": {"list": "list_departments", "retrieve": "get_department", "resolve": "resolve_department", "update": "update_department", "partial_update": "update_department"},
        "ArticleViewSet": {"list": "list_articles", "retrieve": "get_article", "update": "update_article", "partial_update": "update_article"},
        "ShoppingItemViewSet": {"list": "list_shopping_items", "retrieve": "get_shopping_item", "update": "update_shopping_item", "partial_update": "update_shopping_item", "destroy": "delete_shopping_item"},
        "ShoppingListViewSet": {"list": "list_shopping_lists", "retrieve": "get_shopping_list", "create": "create_shopping_list", "update": "update_shopping_list", "partial_update": "update_shopping_list", "destroy": "delete_shopping_list", "add_item": "add_item_to_list", "delete_completed": "delete_completed_items", "reorder": "reorder_shopping_items", "reorder_lists": "reorder_shopping_lists", "import_json": "import_shopping_lists"},
        "RecipeViewSet": {"list": "list_recipes", "retrieve": "get_recipe", "create": "create_recipe", "update": "update_recipe", "partial_update": "update_recipe", "destroy": "delete_recipe", "favorite": "set_recipe_favorite", "add_to_list": "add_recipe_to_list", "reorder_recipes": "reorder_recipes", "reorder_ingredients": "reorder_recipe_ingredients", "reorder_steps": "reorder_recipe_steps", "import_json": "import_recipes"},
        "MealPlanViewSet": {"list": "get_meal_plan_week", "update": "set_meal_plan_recipe", "destroy": "clear_meal_plan_day", "add_to_list": "add_meal_plan_week_to_list"},
    }
    actual = {name: set() for name in expected}
    tools = {tool.name for tool in server.mcp._tool_manager.list_tools()}
    for url in router.urls:
        callback = url.callback
        name = callback.cls.__name__
        if name == "APIRootView":
            continue
        assert name in expected, f"Unmapped REST resource: {name}"
        for action in callback.actions.values():
            actual[name].add(action)
            assert action in expected[name], f"Unmapped REST action: {name}.{action}"
            assert expected[name][action] in tools, f"Missing MCP equivalent: {name}.{action}"
    assert actual == {name: set(actions) for name, actions in expected.items()}
    # The only convenience alias is covered by REST's shopping-item PATCH checked field.
    mapped_tools = {tool for actions in expected.values() for tool in actions.values()}
    assert tools == mapped_tools | {"set_item_checked"}
