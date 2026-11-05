from unittest.mock import patch

import pytest
from django.test import Client
from django.urls import reverse

from easy_kitchen.models import ShoppingItem, ShoppingList


def list_editor_data(shopping_list, **overrides):
    items = list(shopping_list.items.all())
    data = {"title": shopping_list.title, "date": shopping_list.date.isoformat(), "icon": shopping_list.icon,
            "items-TOTAL_FORMS": str(len(items)), "items-INITIAL_FORMS": str(len(items))}
    for index, item in enumerate(items):
        data.update({f"items-{index}-id": str(item.pk), f"items-{index}-name": item.name, f"items-{index}-quantity": item.quantity,
                     f"items-{index}-ORDER": str(index + 1)})
        if item.checked:
            data[f"items-{index}-checked"] = "on"
    return data | overrides


@pytest.mark.django_db
@pytest.mark.parametrize("htmx", [False, True])
def test_list_editor_saves_metadata_and_ordered_items_together(client, user, shopping_list, htmx):
    first = ShoppingItem.objects.create(shopping_list=shopping_list, name="Onion", quantity="1", position=1, checked=True)
    removed = ShoppingItem.objects.create(shopping_list=shopping_list, name="Carrot", position=2)
    client.force_login(user)
    data = list_editor_data(shopping_list, title="Market", date="2026-11-10", icon="flower", **{
        "items-TOTAL_FORMS": "3", "items-0-name": "Red onion", "items-0-quantity": "2", "items-0-ORDER": "2",
        "items-1-DELETE": "on", "items-2-name": "Salt", "items-2-quantity": "1 tsp", "items-2-ORDER": "1",
    })
    response = client.post(reverse("easy_kitchen:update", args=[shopping_list.pk]), data, **({"HTTP_HX_REQUEST": "true"} if htmx else {}))
    assert response.status_code == (200 if htmx else 302)
    if htmx:
        assert response["HX-Push-Url"] == reverse("easy_kitchen:detail", args=[shopping_list.pk])
        assert 'id="list-editor-form"' not in response.content.decode()
    shopping_list.refresh_from_db()
    assert shopping_list.title == "Market" and shopping_list.date.isoformat() == "2026-11-10" and shopping_list.icon == "flower"
    assert list(shopping_list.items.values_list("name", "quantity")) == [("Salt", "1 tsp"), ("Red onion", "2")]
    assert shopping_list.items.get(name="Red onion").pk == first.pk
    assert shopping_list.items.get(name="Red onion").checked
    assert not ShoppingItem.objects.filter(pk=removed.pk).exists()
    assert user.articles.filter(name="Red onion").exists() and user.articles.filter(name="Salt").exists()


@pytest.mark.django_db
@pytest.mark.parametrize("invalid", [{"title": ""}, {"date": "invalid"}, {"items-0-name": ""}])
def test_list_editor_errors_keep_draft_and_database_unchanged(client, user, shopping_list, invalid):
    ShoppingItem.objects.create(shopping_list=shopping_list, name="Onion", quantity="1", checked=True)
    client.force_login(user)
    original = shopping_list.title
    response = client.post(reverse("easy_kitchen:update", args=[shopping_list.pk]), list_editor_data(shopping_list, title="Draft", **invalid) if "title" not in invalid else list_editor_data(shopping_list, **invalid), HTTP_HX_REQUEST="true")
    assert response.status_code == 422
    assert 'id="list-editor-form"' in response.content.decode()
    assert "HX-Push-Url" not in response
    shopping_list.refresh_from_db()
    assert shopping_list.title == original
    item = shopping_list.items.get()
    assert item.name == "Onion" and item.quantity == "1" and item.checked


@pytest.mark.django_db
def test_list_editor_rejects_other_lists_items_and_foreign_lists(client, user, other_user, shopping_list):
    own_item = ShoppingItem.objects.create(shopping_list=shopping_list, name="Onion")
    client.force_login(user)
    for owner in (user, other_user):
        other_list = ShoppingList.objects.create(user=owner, title="Another")
        foreign = ShoppingItem.objects.create(shopping_list=other_list, name="Private")
        response = client.post(reverse("easy_kitchen:update", args=[shopping_list.pk]), list_editor_data(shopping_list, **{"items-0-id": str(foreign.pk), "items-0-name": "Changed"}))
        assert response.status_code == 422
        own_item.refresh_from_db()
        foreign.refresh_from_db()
        assert own_item.name == "Onion" and foreign.name == "Private"
    assert client.get(reverse("easy_kitchen:update", args=[other_list.pk])).status_code == 404


@pytest.mark.django_db
def test_list_editor_is_atomic(client, user, shopping_list):
    ShoppingItem.objects.create(shopping_list=shopping_list, name="Onion")
    original = shopping_list.title
    client.force_login(user)
    with patch.object(ShoppingItem, "save", side_effect=RuntimeError("Item failed")):
        with pytest.raises(RuntimeError, match="Item failed"):
            client.post(reverse("easy_kitchen:update", args=[shopping_list.pk]), list_editor_data(shopping_list, title="Draft"))
    shopping_list.refresh_from_db()
    assert shopping_list.title == original and shopping_list.items.get().name == "Onion"


@pytest.mark.django_db
def test_list_editor_requires_authentication_csrf_and_management_form(client, user, shopping_list):
    url = reverse("easy_kitchen:update", args=[shopping_list.pk])
    assert client.get(url).status_code == 302
    client.force_login(user)
    assert client.post(url, {"title": "Draft", "date": "2026-11-05"}).status_code == 422
    secured = Client(enforce_csrf_checks=True)
    secured.force_login(user)
    assert secured.post(url, list_editor_data(shopping_list)).status_code == 403


@pytest.mark.django_db
def test_list_detail_exposes_only_direct_edit_and_editor_owns_delete(client, user, shopping_list):
    client.force_login(user)
    content = client.get(reverse("easy_kitchen:detail", args=[shopping_list.pk])).content.decode()
    assert "data-edit-toggle" not in content
    assert 'id="delete-list-modal"' not in content
    assert 'aria-label="Delete list"' not in content
    assert f'hx-get="{reverse("easy_kitchen:update", args=[shopping_list.pk])}"' in content
    content = client.get(reverse("easy_kitchen:update", args=[shopping_list.pk])).content.decode()
    assert 'id="delete-list-modal"' in content
    assert 'type="date"' in content
