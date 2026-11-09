import json

import pytest
from django.urls import reverse
from rest_framework.authtoken.models import Token
from easy_kitchen.models import ShoppingList


@pytest.mark.django_db
def test_api_token_only_returns_own_lists(client, user, other_user):
    own = ShoppingList.objects.create(user=user, title="Eigene")
    ShoppingList.objects.create(user=other_user, title="Andere")
    token = Token.objects.create(user=user)
    response = client.get(reverse("shopping-list-list"), HTTP_AUTHORIZATION=f"Token {token.key}")
    assert response.status_code == 200
    assert [record["id"] for record in response.json()] == [own.id]


@pytest.mark.django_db
def test_api_import_creates_list_and_items(client, user):
    token = Token.objects.create(user=user)
    response = client.post(reverse("shopping-list-import-json"), {"lists": [{"title": "Pasta", "date": "2026-10-30", "items": [{"name": "Nudeln", "quantity": "500 g"}]}]}, content_type="application/json", HTTP_AUTHORIZATION=f"Token {token.key}")
    assert response.status_code == 201
    result = response.json()[0]
    assert result["title"] == "Pasta"
    assert result["items"][0]["name"] == "Nudeln"


@pytest.mark.django_db
def test_api_can_reorder_lists_and_recipes(client, user, other_user):
    from easy_kitchen.services import create_recipe

    token = Token.objects.create(user=user)
    first = ShoppingList.objects.create(user=user, title="First")
    second = ShoppingList.objects.create(user=user, title="Second")
    ShoppingList.objects.create(user=other_user, title="Foreign")
    headers = {"HTTP_AUTHORIZATION": f"Token {token.key}"}

    lists = client.post(
        reverse("shopping-list-reorder-lists"),
        json.dumps({"list_ids": [first.pk, second.pk]}),
        content_type="application/json",
        **headers,
    )
    assert lists.status_code == 200
    assert [record["title"] for record in lists.json()] == ["First", "Second"]

    older = create_recipe(user, title="Older")
    newer = create_recipe(user, title="Newer")
    recipes = client.post(
        reverse("recipe-reorder-recipes"),
        json.dumps({"recipe_ids": [older.pk, newer.pk]}),
        content_type="application/json",
        **headers,
    )
    assert recipes.status_code == 200
    assert [record["title"] for record in recipes.json()] == ["Older", "Newer"]


@pytest.mark.django_db
def test_api_can_create_update_reorder_and_delete_a_list(client, user):
    token = Token.objects.create(user=user)
    headers = {"HTTP_AUTHORIZATION": f"Token {token.key}"}
    create_response = client.post(
        reverse("shopping-list-list"),
        json.dumps({
            "title": "Wocheneinkauf",
            "date": "2026-10-30",
            "items": [{"name": "Tofu"}, {"name": "Reis"}],
        }),
        content_type="application/json",
        **headers,
    )
    assert create_response.status_code == 201
    shopping_list = create_response.json()

    update_response = client.patch(
        reverse("shopping-list-detail", args=[shopping_list["id"]]),
        json.dumps({"title": "Wochenendeinkauf"}),
        content_type="application/json",
        **headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "Wochenendeinkauf"

    reversed_ids = [item["id"] for item in reversed(shopping_list["items"])]
    reorder_response = client.post(
        reverse("shopping-list-reorder", args=[shopping_list["id"]]),
        json.dumps({"item_ids": reversed_ids}),
        content_type="application/json",
        **headers,
    )
    assert reorder_response.status_code == 200
    assert [item["id"] for item in reorder_response.json()["items"]] == reversed_ids

    delete_response = client.delete(reverse("shopping-list-detail", args=[shopping_list["id"]]), **headers)
    assert delete_response.status_code == 204


@pytest.mark.django_db
def test_api_put_replaces_list_items(client, user):
    token = Token.objects.create(user=user)
    headers = {"HTTP_AUTHORIZATION": f"Token {token.key}"}
    created = client.post(
        reverse("shopping-list-list"),
        json.dumps({"title": "Wocheneinkauf", "date": "2026-10-30", "items": [{"name": "Tofu"}]}),
        content_type="application/json",
        **headers,
    )
    assert created.status_code == 201
    shopping_list = created.json()

    response = client.put(
        reverse("shopping-list-detail", args=[shopping_list["id"]]),
        json.dumps({
            "title": "Wocheneinkauf",
            "date": "2026-10-30",
            "items": [{"name": "Reis", "quantity": "1 kg"}],
        }),
        content_type="application/json",
        **headers,
    )

    assert response.status_code == 200
    assert [(item["name"], item["quantity"]) for item in response.json()["items"]] == [("Reis", "1 kg")]


@pytest.mark.django_db
def test_browser_shows_swagger_ui(client):
    response = client.get(reverse("swagger-ui"))

    assert response.status_code == 200
    content = response.content.decode()
    assert 'id="swagger-ui"' in content
    assert reverse("api-schema") in content


@pytest.mark.django_db
def test_openapi_schema_lists_every_operation(client, user):
    client.force_login(user)

    response = client.get(reverse("api-schema"), HTTP_ACCEPT="application/json")

    assert response.status_code == 200
    schema = response.json()
    paths = schema["paths"]
    assert set(paths["/api/v1/departments/"]) == {"get"}
    assert set(paths["/api/v1/departments/resolve/"]) == {"get"}
    for resource in ("departments", "articles"):
        assert set(paths[f"/api/v1/{resource}/{{id}}/"]) == {"get", "put", "patch"}
    assert set(paths["/api/v1/shopping-items/{id}/"]) == {"get", "put", "patch", "delete"}
    for path in ("shopping-lists/{id}/add-item", "shopping-lists/{id}/delete-completed", "recipes/{id}/add-to-list"):
        assert set(paths[f"/api/v1/{path}/"]) == {"post"}
    assert set(paths["/api/v1/recipes/{id}/favorite/"]) == {"post"}
    assert set(paths["/api/v1/shopping-lists/"]) >= {"get", "post"}
    assert set(paths["/api/v1/recipes/"]) >= {"get", "post"}
    assert "import_json" in paths["/api/v1/recipes/import_json/"]["post"]["operationId"]
    assert set(paths["/api/v1/shopping-lists/{id}/"]) >= {"get", "put", "patch", "delete"}
    assert "item_ids" in schema["components"]["schemas"]["ReorderItems"]["properties"]
    import_body = paths["/api/v1/shopping-lists/import_json/"]["post"]["requestBody"]
    assert "lists" in str(import_body)


@pytest.mark.django_db
def test_openapi_schema_and_swagger_ui_are_public(client):
    assert client.get(reverse("swagger-ui")).status_code == 200

    response = client.get(reverse("api-schema"), HTTP_ACCEPT="application/json")

    assert response.status_code == 200
    assert "/api/v1/shopping-lists/" in response.json()["paths"]
