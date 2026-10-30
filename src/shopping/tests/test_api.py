import pytest
from django.urls import reverse
from rest_framework.authtoken.models import Token
from shopping.models import ShoppingList


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
