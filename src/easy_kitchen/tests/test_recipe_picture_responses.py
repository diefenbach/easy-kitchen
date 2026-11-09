import pytest
from asgiref.sync import async_to_sync
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from easy_kitchen import mcp_server as server
from easy_kitchen.api.serializers import RecipeSerializer
from easy_kitchen.services import create_recipe
from easy_kitchen.tests.test_mcp import authorization_context

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.parametrize("backend", ["api", "mcp"])
@pytest.mark.parametrize("picture", ["none", "external", "upload"])
def test_recipe_responses_only_expose_the_selected_picture_url(user, backend, picture):
    recipe = create_recipe(user, title="Soup", image_url="" if picture == "none" else "https://example.com/soup.jpg")
    if picture == "upload":
        recipe.image = "recipes/upload.jpg"
        recipe.save(update_fields=["image"])
    token = Token.objects.create(user=user)
    ctx = authorization_context(token)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    expected = recipe.image_url
    if picture == "upload":
        expected = ("http://testserver" if backend == "api" else "") + recipe.image.url
    if backend == "api":
        responses = [client.get(reverse("recipe-detail", args=[recipe.pk])).json()]
        responses += [client.get(reverse("recipe-list"), params).json()[0] for params in ({}, {"summary": True})]
    else:
        call = async_to_sync(server.mcp._tool_manager.call_tool)
        responses = [call("get_recipe", {"recipe_id": recipe.pk}, ctx)]
        responses += [call("list_recipes", params, ctx)[0] for params in ({}, {"summary": True})]
    for data in responses:
        assert data["picture_url"] == expected
        assert "image" not in data and "image_url" not in data


@pytest.mark.parametrize("backend", ["api", "mcp"])
def test_external_image_url_remains_writable_but_is_not_echoed(user, backend):
    token = Token.objects.create(user=user)
    if backend == "api":
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        created = client.post(reverse("recipe-list"), {"title": "Soup", "image_url": "https://example.com/first.jpg"}, format="json")
        assert created.status_code == 201
        data = created.json()
        changed = client.patch(reverse("recipe-detail", args=[data["id"]]), {"image_url": "https://example.com/second.jpg"}, format="json")
        assert changed.status_code == 200
        updated = changed.json()
    else:
        ctx = authorization_context(token)
        data = server.create_recipe(ctx=ctx, title="Soup", image_url="https://example.com/first.jpg")
        updated = server.update_recipe(ctx=ctx, recipe_id=data["id"], changes={"image_url": "https://example.com/second.jpg"})
    for result, url in ((data, "https://example.com/first.jpg"), (updated, "https://example.com/second.jpg")):
        assert result["picture_url"] == url
        assert "image" not in result and "image_url" not in result


def test_recipe_api_schema_marks_external_image_url_as_input_only():
    serializer = RecipeSerializer()
    assert "image" not in serializer.fields
    assert serializer.fields["image_url"].write_only
    assert serializer.fields["picture_url"].read_only
