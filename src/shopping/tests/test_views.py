import pytest
from django.test import Client
from django.urls import reverse
from datetime import date
from shopping.models import ShoppingItem, ShoppingList


@pytest.mark.django_db
def test_lists_are_scoped_to_current_user(client, user, other_user):
    own = ShoppingList.objects.create(user=user, title="Meine")
    ShoppingList.objects.create(user=other_user, title="Fremde")
    client.force_login(user)
    response = client.get(reverse("shopping:list"))
    assert response.status_code == 200
    assert "Meine" in response.content.decode()
    assert "Fremde" not in response.content.decode()
    assert client.get(reverse("shopping:detail", args=[own.pk])).status_code == 200


@pytest.mark.django_db
def test_user_cannot_access_other_list(client, user, other_user):
    other_list = ShoppingList.objects.create(user=other_user, title="Privat")
    client.force_login(user)
    assert client.get(reverse("shopping:detail", args=[other_list.pk])).status_code == 404


@pytest.mark.django_db
def test_htmx_item_create_and_toggle(client, user, shopping_list):
    client.force_login(user)
    response = client.post(reverse("shopping:item-create", args=[shopping_list.pk]), {"name": "Tofu", "quantity": "400 g"}, HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    item = ShoppingItem.objects.get(shopping_list=shopping_list)
    response = client.post(reverse("shopping:item-toggle", args=[shopping_list.pk, item.pk]), HTTP_HX_REQUEST="true")
    item.refresh_from_db()
    assert item.checked is True
    assert "☑" in response.content.decode()


@pytest.mark.django_db
def test_item_toggle_requires_and_accepts_csrf_token(client, user, shopping_list):
    item = ShoppingItem.objects.create(shopping_list=shopping_list, name="Tofu")
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(user)
    detail_response = csrf_client.get(reverse("shopping:detail", args=[shopping_list.pk]))
    assert "htmx:configRequest" in detail_response.content.decode()
    assert csrf_client.post(
        reverse("shopping:item-toggle", args=[shopping_list.pk, item.pk]),
        HTTP_HX_REQUEST="true",
    ).status_code == 403
    token = csrf_client.cookies["csrftoken"].value
    response = csrf_client.post(
        reverse("shopping:item-toggle", args=[shopping_list.pk, item.pk]),
        HTTP_HX_REQUEST="true",
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 200
    item.refresh_from_db()
    assert item.checked is True


@pytest.mark.django_db
def test_login_displays_invalid_credentials_error(client):
    response = client.post(reverse("login"), {"username": "unknown", "password": "wrong"})
    assert response.status_code == 200
    assert "alert-danger" in response.content.decode()


@pytest.mark.django_db
def test_list_detail_uses_modal_delete_confirmations(client, user, shopping_list):
    ShoppingItem.objects.create(shopping_list=shopping_list, name="Tofu")
    client.force_login(user)

    response = client.get(reverse("shopping:detail", args=[shopping_list.pk]))

    content = response.content.decode()
    assert 'data-bs-target="#delete-list-modal"' in content
    assert 'data-bs-target="#delete-item-modal-' in content
    assert "hx-confirm" not in content


@pytest.mark.django_db
def test_edit_list_prefills_html_date_input(client, user, shopping_list):
    shopping_list.date = date(2026, 10, 30)
    shopping_list.save()
    client.force_login(user)

    response = client.get(reverse("shopping:update", args=[shopping_list.pk]))

    assert '<input type="date" name="date" value="2026-10-30"' in response.content.decode()


@pytest.mark.django_db
def test_reset_checked_items_marks_all_items_as_open(client, user, shopping_list):
    completed = ShoppingItem.objects.create(shopping_list=shopping_list, name="Tofu", checked=True)
    open_item = ShoppingItem.objects.create(shopping_list=shopping_list, name="Reis")
    client.force_login(user)

    response = client.post(reverse("shopping:items-reset-checked", args=[shopping_list.pk]))

    assert response.status_code == 302
    completed.refresh_from_db()
    open_item.refresh_from_db()
    assert completed.checked is False
    assert open_item.checked is False
