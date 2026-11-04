from datetime import date

import pytest
from asgiref.sync import async_to_sync
from mcp.server.mcpserver.exceptions import ToolError
from rest_framework.authtoken.models import Token

from easy_kitchen import mcp_server as server
from easy_kitchen.models import MealPlanEntry, ShoppingList
from easy_kitchen.services import create_recipe, set_meal_plan_recipe
from easy_kitchen.tests.test_mcp import authorization_context

pytestmark = pytest.mark.django_db


@pytest.fixture
def ctx(user):
    return authorization_context(Token.objects.create(user=user))


def test_mcp_reads_sets_replaces_and_clears_only_the_owners_plan(ctx, user, other_user):
    soup = create_recipe(user, title="Soup")
    salad = create_recipe(user, title="Salad")
    private = create_recipe(other_user, title="Private")
    day = date(2027, 1, 1)
    set_meal_plan_recipe(other_user, day, private)
    assert server.set_meal_plan_recipe(day, ctx, recipe_id=soup.pk)["recipe"]["id"] == soup.pk
    assert server.set_meal_plan_recipe(day, ctx, recipe_title="salad")["recipe"]["id"] == salad.pk
    assert MealPlanEntry.objects.filter(user=user).count() == 1
    week = server.get_meal_plan_week(ctx, week=day)
    assert week["week_start"] == "2026-12-28"
    assert week["week_end"] == "2027-01-03"
    assert len(week["days"]) == 7
    assert week["days"][4]["recipe"] == {"id": salad.pk, "title": "Salad"}
    assert week["days"][0]["recipe"] is None
    assert "Private" not in str(week)
    with pytest.raises(ToolError, match="Recipe not found"):
        server.set_meal_plan_recipe(day, ctx, recipe_id=private.pk)
    for _ in range(2):
        assert server.clear_meal_plan_day(day, ctx) == {"date": "2027-01-01", "recipe": None}
    assert not MealPlanEntry.objects.filter(user=user).exists()
    assert MealPlanEntry.objects.get(user=other_user).recipe == private


def test_mcp_recipe_selection_must_be_owned_and_unambiguous(ctx, user):
    create_recipe(user, title="Soup")
    create_recipe(user, title="Soup")
    with pytest.raises(ToolError, match="more than one recipe"):
        server.set_meal_plan_recipe(date(2027, 1, 1), ctx, recipe_title="Soup")
    with pytest.raises(ToolError, match="Choose a recipe"):
        server.set_meal_plan_recipe(date(2027, 1, 1), ctx)
    assert not MealPlanEntry.objects.exists()


@pytest.mark.parametrize("existing", [False, True])
def test_mcp_copies_the_selected_week_to_an_owned_list(ctx, user, other_user, existing):
    day = date(2027, 1, 1)
    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Onion", "quantity": "2"}])
    for planned_day in (date(2026, 12, 28), day, date(2027, 1, 4)):
        set_meal_plan_recipe(user, planned_day, recipe)
    private = create_recipe(other_user, title="Private", ingredients=[{"name": "Secret"}])
    set_meal_plan_recipe(other_user, day, private)
    target = ShoppingList.objects.create(user=user, title="Shop") if existing else None
    kwargs = {"list_id": target.pk} if target else {"title": "Shop"}
    result = server.add_meal_plan_week_to_list(day, ctx, **kwargs)
    assert [(item["name"], item["quantity"]) for item in result["items"]] == [("Onion", "4")]
    assert ShoppingList.objects.get(pk=result["id"]).user == user
    assert MealPlanEntry.objects.filter(user=user).count() == 3
    if existing:
        repeated = server.add_meal_plan_week_to_list(day, ctx, **kwargs)
        assert repeated["items"][0]["quantity"] == "8"


def test_mcp_copy_validates_target_and_empty_weeks_without_creating_lists(ctx, user, other_user):
    day = date(2027, 1, 1)
    with pytest.raises(ToolError, match="no planned recipes"):
        server.add_meal_plan_week_to_list(day, ctx, title="Empty")
    assert not ShoppingList.objects.filter(user=user).exists()
    foreign = ShoppingList.objects.create(user=other_user, title="Private")
    with pytest.raises(ToolError, match="Shopping list not found"):
        server.add_meal_plan_week_to_list(day, ctx, list_id=foreign.pk)
    for kwargs in ({}, {"list_id": foreign.pk, "title": "New"}):
        with pytest.raises(ToolError, match="exactly one"):
            server.add_meal_plan_week_to_list(day, ctx, **kwargs)
    assert not foreign.items.exists()
    assert not ShoppingList.objects.filter(user=user).exists()


def test_mcp_rejects_weeks_outside_the_calendar(ctx):
    with pytest.raises(ToolError, match="complete calendar week"):
        server.get_meal_plan_week(ctx, week=date.max)
    with pytest.raises(ToolError, match="complete calendar week"):
        server.add_meal_plan_week_to_list(date.max, ctx, title="Invalid")
    assert not ShoppingList.objects.exists()


@pytest.mark.parametrize("name,kwargs", [
    ("get_meal_plan_week", {}),
    ("set_meal_plan_recipe", {"date": date(2027, 1, 1), "recipe_id": 1}),
    ("clear_meal_plan_day", {"date": date(2027, 1, 1)}),
    ("add_meal_plan_week_to_list", {"week": date(2027, 1, 1), "title": "Shop"}),
])
def test_mcp_planner_tools_reject_unknown_tokens(name, kwargs):
    context = authorization_context(Token(key="unknown"))
    with pytest.raises(ToolError, match="token is invalid"):
        getattr(server, name)(ctx=context, **kwargs)
    assert not ShoppingList.objects.exists()
    assert not MealPlanEntry.objects.exists()


def test_mcp_planner_tool_schemas_never_expose_the_user():
    expected = {
        "get_meal_plan_week": {"week"},
        "set_meal_plan_recipe": {"date", "recipe_id", "recipe_title"},
        "clear_meal_plan_day": {"date"},
        "add_meal_plan_week_to_list": {"week", "list_id", "title"},
    }
    tools = {tool.name: tool for tool in server.mcp._tool_manager.list_tools()}
    for name, properties in expected.items():
        assert set(tools[name].parameters["properties"]) == properties
    assert tools["get_meal_plan_week"].annotations.read_only_hint
    assert tools["set_meal_plan_recipe"].annotations.destructive_hint
    assert tools["clear_meal_plan_day"].annotations.destructive_hint
    assert not tools["add_meal_plan_week_to_list"].annotations.idempotent_hint


@pytest.mark.django_db(transaction=True)
def test_registered_mcp_tool_parses_iso_dates_and_rejects_invalid_dates(ctx, user):
    recipe = create_recipe(user, title="Soup")
    call_tool = async_to_sync(server.mcp._tool_manager.call_tool)
    result = call_tool(
        "set_meal_plan_recipe", {"date": "2027-01-01", "recipe_id": recipe.pk}, ctx
    )
    assert result["date"] == "2027-01-01"
    assert result["recipe"]["id"] == recipe.pk
    with pytest.raises(ToolError):
        call_tool("set_meal_plan_recipe", {"date": "2027-02-30", "recipe_id": recipe.pk}, ctx)
    assert MealPlanEntry.objects.filter(user=user).count() == 1
