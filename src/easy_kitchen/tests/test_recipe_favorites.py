from urllib.parse import parse_qs, urlsplit

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import translation

from easy_kitchen.models import Recipe
from easy_kitchen.services import create_recipe


@pytest.mark.django_db
@pytest.mark.parametrize(("query", "favorites", "expected"), [
    (" SOUP ", "", ["Tomato soup"]),
    ("summer", "", ["Tomato soup", "Green salad"]),
    ("SUMMER tomato", "", ["Tomato soup"]),
    ("tomato summer", "1", ["Tomato soup"]),
    ("", "1", ["Tomato soup"]),
    ("salad", "1", []),
    ("secret ingredient", "", []),
    ("", "", ["Tomato soup", "Green salad"]),
])
def test_recipe_search_and_favorites_are_combined_and_scoped(client, user, other_user, query, favorites, expected):
    soup = create_recipe(user, title="Tomato soup", description="A summer dinner")
    soup.is_favorite = True
    soup.save(update_fields=["is_favorite"])
    create_recipe(user, title="Green salad", description="Summer lunch", ingredients=[{"name": "secret ingredient"}], steps=[{"text": "secret ingredient"}])
    Recipe.objects.create(user=other_user, title="Private summer tomato soup", is_favorite=True)
    client.force_login(user)

    response = client.get(reverse("easy_kitchen:recipes"), {"q": query, "favorites": favorites})

    assert response.status_code == 200
    assert sorted(recipe.title for recipe in response.context["recipes"]) == sorted(expected)
    assert response.context["search_query"] == query.strip()
    assert response.context["favorites_only"] == (favorites == "1")
    if not expected:
        assert "No matching recipes" in response.content.decode()
        assert "No recipes yet" not in response.content.decode()
    if query.strip() or favorites == "1":
        assert "data-card-reorder=" not in response.content.decode()


@pytest.mark.django_db
def test_favorite_changes_persist_preserve_filters_and_are_idempotent(client, user):
    recipe = Recipe.objects.create(user=user, title="Soup")
    assert recipe.is_favorite is False
    client.force_login(user)
    url = reverse("easy_kitchen:recipe-favorite", args=[recipe.pk])
    data = {"is_favorite": "1", "q": "Soup & lunch", "favorites": "1", "return_to": "overview"}
    for _ in range(2):
        response = client.post(url, data)
        assert response.status_code == 302
    recipe.refresh_from_db()
    assert recipe.is_favorite is True
    assert urlsplit(response.url).path == reverse("easy_kitchen:recipes")
    assert parse_qs(urlsplit(response.url).query) == {"q": ["Soup & lunch"], "favorites": ["1"]}
    response = client.post(url, {"is_favorite": "0", "return_to": "detail"})
    recipe.refresh_from_db()
    assert recipe.is_favorite is False
    assert response.url == reverse("easy_kitchen:recipe-detail", args=[recipe.pk])
    response = client.post(url, {"is_favorite": "1", "return_to": "https://example.com"})
    assert urlsplit(response.url).path == reverse("easy_kitchen:recipes")


@pytest.mark.django_db
def test_favorites_require_authentication_ownership_post_and_csrf(client, user, other_user):
    recipe = Recipe.objects.create(user=user, title="Soup")
    foreign = Recipe.objects.create(user=other_user, title="Private")
    url = reverse("easy_kitchen:recipe-favorite", args=[recipe.pk])
    assert client.post(url, {"is_favorite": "1"}).status_code == 302
    client.force_login(user)
    assert client.get(url).status_code == 405
    assert client.post(reverse("easy_kitchen:recipe-favorite", args=[foreign.pk]), {"is_favorite": "1"}).status_code == 404
    for value in ("", "true", "wrong"):
        assert client.post(url, {"is_favorite": value}).status_code == 400
    secured = Client(enforce_csrf_checks=True)
    secured.force_login(user)
    assert secured.post(url, {"is_favorite": "1"}).status_code == 403
    recipe.refresh_from_db()
    foreign.refresh_from_db()
    assert not recipe.is_favorite and not foreign.is_favorite


@pytest.mark.django_db
def test_favorites_and_filters_have_german_labels(client, user):
    Recipe.objects.create(user=user, title="Soup")
    client.force_login(user)
    with translation.override("de"):
        response = client.get(reverse("easy_kitchen:recipes"))
    content = response.content.decode()
    assert "Nur Favoriten" in content
    assert "Zu Favoriten hinzufügen" in content
    assert "Titel und Beschreibung durchsuchen" in content
