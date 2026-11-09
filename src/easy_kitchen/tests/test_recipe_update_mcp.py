import pytest
from asgiref.sync import async_to_sync
from mcp.server.mcpserver.exceptions import ToolError
from rest_framework.authtoken.models import Token

from easy_kitchen import mcp_server as server
from easy_kitchen.services import create_recipe
from easy_kitchen.tests.test_mcp import authorization_context

pytestmark = pytest.mark.django_db


@pytest.fixture
def ctx(user):
    return authorization_context(Token.objects.create(user=user))


@pytest.fixture
def recipe(user):
    return create_recipe(
        user, title="Tofu", description="Dinner", calories=1250, protein=100,
        preparation_minutes=30, image_url="https://example.com/tofu.jpg",
        ingredients=[{"name": "Tofu", "quantity": "400 g"}], steps=[{"text": "Fry"}],
    )


def test_update_nutrition_preserves_omitted_fields_and_recipe_identity(ctx, recipe):
    before = server._recipe_payload(recipe)
    ingredient_id = recipe.ingredients.get().pk
    step_id = recipe.steps.get().pk
    for _ in range(2):
        result = server.update_recipe(ctx, recipe_id=recipe.pk, changes={"fat": 65, "carbohydrates": 50})
        assert {k: v for k, v in result.items() if k != "updated_at"} == {k: v for k, v in {**before, "fat": 65, "carbohydrates": 50}.items() if k != "updated_at"}
    recipe.refresh_from_db()
    assert recipe.fat == 65
    assert recipe.carbohydrates == 50
    assert recipe.ingredients.get().pk == ingredient_id
    assert recipe.steps.get().pk == step_id
    assert recipe.user.recipes.count() == 1


def test_update_can_rename_replace_lines_and_clear_values(ctx, recipe):
    result = server.update_recipe(ctx, recipe_title=" tofu ", changes={
        "title": "Tofu bowl", "description": "", "image_url": "", "protein": None,
        "calories": 0, "preparation_minutes": None,
        "ingredients": [{"name": "Rice", "quantity": "100 g"}], "steps": [],
    })
    assert result["title"] == "Tofu bowl"
    assert result["description"] == result["picture_url"] == ""
    assert result["protein"] is result["preparation_minutes"] is None
    assert result["calories"] == 0
    assert [(line["name"], line["quantity"]) for line in result["ingredients"]] == [("Rice", "100 g")]
    assert result["steps"] == []
    result = server.update_recipe(ctx, recipe_id=recipe.pk, changes={"ingredients": []})
    assert result["ingredients"] == []


def test_update_rejects_foreign_missing_and_ambiguous_recipes(ctx, recipe, other_user):
    foreign = create_recipe(other_user, title="Secret", fat=10)
    for recipe_id in (foreign.pk, 999999):
        with pytest.raises(ToolError, match="Recipe not found"):
            server.update_recipe(ctx, recipe_id=recipe_id, changes={"fat": 20})
    foreign.refresh_from_db()
    assert foreign.fat == 10
    create_recipe(recipe.user, title=recipe.title)
    with pytest.raises(ToolError, match="more than one recipe"):
        server.update_recipe(ctx, recipe_title=recipe.title, changes={"fat": 20})
    with pytest.raises(ToolError, match="Choose a recipe"):
        server.update_recipe(ctx, changes={"fat": 20})


@pytest.mark.parametrize("changes", [
    {"title": " "}, {"image_url": "invalid"}, {"fat": -1},
    {"user": 123}, {"title": None}, {"ingredients": None},
    {"steps": [{"text": ""}]}, {"ingredients": [{"name": "x" * 256}]},
])
def test_invalid_update_preserves_existing_recipe(ctx, recipe, changes):
    before = server._recipe_payload(recipe)
    with pytest.raises(ToolError):
        server.update_recipe(ctx, recipe_id=recipe.pk, changes=changes)
    recipe.refresh_from_db()
    assert server._recipe_payload(recipe) == before


def test_update_requires_authentication(recipe):
    with pytest.raises(ToolError):
        server.update_recipe(authorization_context(Token(key="missing")), recipe_id=recipe.pk, changes={"fat": 20})


def test_update_tool_schema():
    tool = next(t for t in server.mcp._tool_manager.list_tools() if t.name == "update_recipe")
    assert set(tool.parameters["properties"]) == {"recipe_id", "recipe_title", "changes"}
    assert tool.annotations.idempotent_hint is True
    assert tool.annotations.destructive_hint is True


@pytest.mark.django_db(transaction=True)
def test_registered_update_tool_preserves_omitted_fields_and_clears_explicit_null(ctx, recipe):
    call_tool = async_to_sync(server.mcp._tool_manager.call_tool)
    result = call_tool("update_recipe", {"recipe_id": recipe.pk, "changes": {"protein": None, "fat": 65}}, ctx)
    assert result["protein"] is None
    assert result["fat"] == 65
    assert result["calories"] == 1250
    assert [(line["name"], line["quantity"]) for line in result["ingredients"]] == [("Tofu", "400 g")]
    with pytest.raises(ToolError):
        call_tool("update_recipe", {"recipe_id": recipe.pk, "changes": {"fat": -1}}, ctx)
