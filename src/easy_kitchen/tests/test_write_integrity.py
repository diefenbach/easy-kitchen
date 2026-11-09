from datetime import date
from unittest.mock import patch

import pytest
from django.urls import reverse

from easy_kitchen.models import Recipe, ShoppingList
from easy_kitchen.services import (
    add_recipe_to_owned_list, create_item, create_recipe, create_shopping_list,
)


@pytest.mark.django_db
@pytest.mark.parametrize("payload", [{"items": [{}]}, {"items": [{"quantity": "2 l"}]}])
def test_partial_list_replacement_requires_complete_children(client, user, payload):
    shopping_list = create_shopping_list(user, title="Original", date=date.today())
    item = create_item(shopping_list, name="Milk", quantity="1 l")
    client.force_login(user)
    response = client.patch(reverse("shopping-list-detail", args=[shopping_list.pk]),
                            payload, content_type="application/json")
    assert response.status_code == 400
    assert "name" in response.json()["items"][0]
    assert list(shopping_list.items.values_list("pk", "quantity")) == [(item.pk, "1 l")]


@pytest.mark.django_db
@pytest.mark.parametrize("field,child", [("ingredients", {"quantity": "2 l"}), ("steps", {})])
def test_partial_recipe_replacement_preserves_children_on_error(client, user, field, child):
    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Water"}], steps=["Boil"])
    before = (list(recipe.ingredients.values()), list(recipe.steps.values()))
    client.force_login(user)
    response = client.patch(reverse("recipe-detail", args=[recipe.pk]),
                            {field: [child]}, content_type="application/json")
    assert response.status_code == 400
    assert (list(recipe.ingredients.values()), list(recipe.steps.values())) == before


@pytest.mark.django_db
def test_omitted_collections_are_preserved_and_empty_collections_clear(client, user):
    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Water"}], steps=["Boil"])
    shopping_list = create_shopping_list(user, title="Shop", date=date.today(), items=[{"name": "Milk"}])
    client.force_login(user)
    for name, obj, fields in [("recipe-detail", recipe, ["ingredients", "steps"]),
                              ("shopping-list-detail", shopping_list, ["items"])]:
        url = reverse(name, args=[obj.pk])
        assert client.patch(url, {"title": "Renamed"}, content_type="application/json").status_code == 200
        assert all(getattr(obj, field).exists() for field in fields)
        assert client.patch(url, {field: [] for field in fields}, content_type="application/json").status_code == 200
        assert all(not getattr(obj, field).exists() for field in fields)


@pytest.mark.django_db
def test_list_replacement_rolls_back_metadata_and_items(client, user):
    shopping_list = create_shopping_list(user, title="Original", date=date.today(), items=[{"name": "Milk"}])
    original_ids = list(shopping_list.items.values_list("pk", flat=True))
    client.force_login(user)
    with patch("easy_kitchen.services.create_item", side_effect=RuntimeError("write failed")):
        with pytest.raises(RuntimeError):
            client.patch(reverse("shopping-list-detail", args=[shopping_list.pk]),
                         {"title": "Changed", "items": [{"name": "Bread"}]}, content_type="application/json")
    shopping_list.refresh_from_db()
    assert shopping_list.title == "Original"
    assert list(shopping_list.items.values_list("pk", flat=True)) == original_ids


@pytest.mark.django_db
def test_list_creation_rolls_back_parent_and_positions(user):
    existing = create_shopping_list(user, title="Existing", date=date.today())
    with patch("easy_kitchen.services.create_item", side_effect=RuntimeError("write failed")):
        with pytest.raises(RuntimeError):
            create_shopping_list(user, title="Broken", date=date.today(), items=[{"name": "Milk"}])
    existing.refresh_from_db()
    assert existing.position == 1
    assert list(ShoppingList.objects.values_list("title", flat=True)) == ["Existing"]


@pytest.mark.django_db
def test_recipe_create_and_update_roll_back_all_lines(user):
    existing = create_recipe(user, title="Existing", ingredients=[{"name": "Water"}], steps=["Boil"])
    for recipe in [None, existing]:
        with patch("easy_kitchen.services._write_lines", side_effect=RuntimeError("write failed")):
            with pytest.raises(RuntimeError):
                create_recipe(user, recipe=recipe, title="Broken", ingredients=[{"name": "Salt"}], steps=["Mix"])
        existing.refresh_from_db()
        assert existing.title == "Existing"
        assert existing.position == 1
        assert list(existing.ingredients.values_list("name", flat=True)) == ["Water"]
        assert Recipe.objects.count() == 1


@pytest.mark.django_db
def test_copy_recipe_rolls_back_new_target_and_partial_items(user):
    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Milk"}, {"name": "Salt"}])
    real_create = create_item
    def fail_second(shopping_list, **kwargs):
        if kwargs["name"] == "Salt":
            raise RuntimeError("write failed")
        return real_create(shopping_list, **kwargs)
    with patch("easy_kitchen.services.create_item", side_effect=fail_second):
        with pytest.raises(RuntimeError):
            add_recipe_to_owned_list(user, recipe_id=recipe.pk, list_title="New")
    assert not ShoppingList.objects.exists()
    assert not user.articles.exists()


@pytest.mark.django_db
def test_web_recipe_copy_rolls_back_new_target(client, user):
    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Salt"}])
    client.force_login(user)
    with patch("easy_kitchen.services.create_item", side_effect=RuntimeError("write failed")):
        with pytest.raises(RuntimeError):
            client.post(reverse("easy_kitchen:recipe-add-to-list", args=[recipe.pk]), {"title": "New"})
    assert not ShoppingList.objects.exists()


@pytest.mark.django_db
def test_api_quantity_overflow_is_validation_error_and_leaves_no_parent(client, user):
    client.force_login(user)
    response = client.post(reverse("shopping-list-list"), {
        "title": "Too long", "date": "2026-11-06",
        "items": [{"name": "Milk", "quantity": "1 " + "a" * 98},
                  {"name": "Milk", "quantity": "1 " + "b" * 98}],
    }, content_type="application/json")
    assert response.status_code == 400
    assert "quantity" in response.json()
    assert not ShoppingList.objects.exists()
