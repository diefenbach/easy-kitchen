from types import SimpleNamespace
import json

import pytest
from asgiref.sync import async_to_sync
from django.urls import reverse
from mcp.server.mcpserver.exceptions import ToolError
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from easy_kitchen import mcp_server as server
from easy_kitchen.api.serializers import RecipeSerializer
from easy_kitchen.services import create_item, create_recipe
from easy_kitchen.tests.test_mcp import authorization_context

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(params=["api", "mcp"])
def interface(request, user):
    token = Token.objects.create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    ctx = authorization_context(token)

    def call(tool, route, data, *, pk=None, selector="recipe_id", changes=False):
        if request.param == "api":
            url = reverse(route, args=[pk] if pk is not None else [])
            response = (client.patch if changes else client.post)(url, data, format="json")
            return response.status_code < 400, response.json()
        args = {"changes": data} if changes else dict(data)
        if pk is not None:
            args[selector] = pk
        try:
            return True, async_to_sync(server.mcp._tool_manager.call_tool)(tool, args, ctx)
        except ToolError as error:
            return False, str(error)

    return call


@pytest.mark.parametrize("data", [
    {"title": "   ", "date": "2027-01-01"},
    {"title": "Shop", "date": "2027-01-01", "unknown": True},
    {"title": "Shop", "date": "2027-01-01", "items": [{"name": "  "}]},
])
def test_list_creation_rejects_invalid_input_without_writes(interface, user, data):
    success, _ = interface("create_shopping_list", "shopping-list-list", data)
    assert not success
    assert not user.shopping_lists.exists() and not user.articles.exists()


@pytest.mark.parametrize("data", [
    {"ingredients": [{"name": "   "}]}, {"steps": [{"text": "\n "}]},
    {"description": "x" * 5001}, {"fats": 10}, {"fat": True}, {"fat": 1.5},
    {"fat": -1}, {"fat": 2147483648},
])
def test_recipe_updates_reject_invalid_input_without_losing_data(interface, user, data):
    recipe = create_recipe(user, title="Soup", fat=10,
                           ingredients=[{"name": "Salt"}], steps=["Cook"])
    before = (list(recipe.ingredients.values()), list(recipe.steps.values()))
    success, _ = interface("update_recipe", "recipe-detail", data, pk=recipe.pk, changes=True)
    assert not success
    recipe.refresh_from_db()
    assert recipe.fat == 10
    assert (list(recipe.ingredients.values()), list(recipe.steps.values())) == before


def test_api_stale_partial_update_preserves_intervening_mcp_write(user):
    recipe = create_recipe(user, title="Soup", calories=100)
    pending = RecipeSerializer(recipe, data={"title": "Dinner"}, partial=True,
                               context={"request": SimpleNamespace(user=user)})
    assert pending.is_valid(), pending.errors
    ctx = authorization_context(Token.objects.create(user=user))
    server.update_recipe(ctx, recipe_id=recipe.pk, changes={"fat": 65})
    pending.save()
    recipe.refresh_from_db()
    assert recipe.title == "Dinner" and recipe.fat == 65 and recipe.calories == 100


def test_mcp_item_responses_use_one_shape(user, shopping_list):
    ctx = authorization_context(Token.objects.create(user=user))
    added = server.add_item_to_list(name="Tofu", list_id=shopping_list.pk, ctx=ctx)
    updated = server.update_shopping_item(item_id=added["id"], changes={"quantity": "1"}, ctx=ctx)
    checked = server.set_item_checked(name="Tofu", list_id=shopping_list.pk, ctx=ctx)
    listed = server.list_shopping_lists(ctx)[0]["items"][0]
    assert set(added) == set(updated) == set(checked) == set(listed)


def test_mcp_recipe_metadata_includes_child_ids_positions_and_picture(user):
    recipe = create_recipe(user, title="Soup", image_url="https://example.com/soup.jpg",
                           ingredients=[{"name": "Salt"}], steps=["Cook"])
    ctx = authorization_context(Token.objects.create(user=user))
    data = server.list_recipes(ctx)[0]
    assert data["picture_url"] == recipe.image_url
    assert data["ingredients"][0]["id"] == recipe.ingredients.get().pk
    assert data["steps"][0]["position"] == 1


def test_checking_by_name_does_not_choose_an_arbitrary_duplicate(user, shopping_list):
    first = create_item(shopping_list, name="Tofu")
    second = create_item(shopping_list, name="Rice")
    server.update_shopping_item(item_id=second.pk, changes={"name": "Tofu"},
                               ctx=authorization_context(Token.objects.create(user=user)))
    ctx = authorization_context(Token.objects.get(user=user))
    with pytest.raises(ToolError, match="more than one"):
        server.set_item_checked(name="Tofu", list_id=shopping_list.pk, ctx=ctx)
    result = server.set_item_checked(item_id=second.pk, ctx=ctx)
    assert result["id"] == second.pk
    first.refresh_from_db()
    assert not first.checked


def test_service_error_codes_match_for_foreign_recipe_updates(user, other_user):
    foreign = create_recipe(other_user, title="Private")
    token = Token.objects.create(user=user)
    ctx = authorization_context(token)
    with pytest.raises(ToolError) as caught:
        server.update_recipe(ctx, recipe_id=foreign.pk, changes={"fat": 10})
    assert json.loads(str(caught.value))["code"] == "not_found"
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    response = client.patch(reverse("recipe-detail", args=[foreign.pk]), {"fat": 10}, format="json")
    assert response.status_code == 404 and response.json()["code"] == "not_found"


def test_overflow_error_codes_match(user, shopping_list):
    create_item(shopping_list, name="Milk", quantity="1 " + "a" * 98)
    token = Token.objects.create(user=user)
    ctx = authorization_context(token)
    data = {"name": "Milk", "quantity": "1 " + "b" * 98}
    with pytest.raises(ToolError) as caught:
        server.add_item_to_list(ctx=ctx, list_id=shopping_list.pk, **data)
    assert json.loads(str(caught.value))["code"] == "quantity_overflow"
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    response = client.post(reverse("shopping-list-add-item", args=[shopping_list.pk]), data, format="json")
    assert response.status_code == 400 and response.json()["code"] == "quantity_overflow"


def test_rest_and_mcp_read_the_same_recipe_and_list_shapes(user, shopping_list):
    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Salt"}], steps=["Cook"])
    create_item(shopping_list, name="Tofu", quantity="400 g")
    token = Token.objects.create(user=user)
    ctx = authorization_context(token)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    assert client.get(reverse("recipe-detail", args=[recipe.pk])).json() == server.list_recipes(ctx)[0]
    assert client.get(reverse("shopping-list-detail", args=[shopping_list.pk])).json() == server.list_shopping_lists(ctx)[0]


def test_registered_tools_reject_unknown_root_arguments():
    assert all(tool.parameters.get("additionalProperties") is False
               for tool in server.mcp._tool_manager.list_tools())


def test_api_list_creation_honors_its_optional_date(user):
    from django.utils import timezone

    client = APIClient()
    client.force_authenticate(user)
    response = client.post(reverse("shopping-list-list"), {"title": "Today"}, format="json")
    assert response.status_code == 201
    assert response.json()["date"] == timezone.localdate().isoformat()


@pytest.mark.parametrize("value", [None, 0, 2147483647])
def test_valid_nutrition_boundaries_are_shared(interface, user, value):
    recipe = create_recipe(user, title="Soup")
    success, result = interface("update_recipe", "recipe-detail", {"fat": value}, pk=recipe.pk, changes=True)
    assert success and result["fat"] == value
