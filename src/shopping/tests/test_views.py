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
    assert 'role="group" aria-label="Item actions"' in content
    assert "hx-confirm" not in content


@pytest.mark.django_db
def test_list_detail_uses_a_minimal_icon_header(client, user, shopping_list):
    client.force_login(user)

    response = client.get(reverse("shopping:detail", args=[shopping_list.pk]))

    content = response.content.decode()
    assert 'class="btn btn-outline-secondary btn-sm list-back-button mb-3"' in content
    assert 'class="list-detail-header card border-0 mb-4"' in content
    assert "bi-arrow-left" in content
    assert "bi-calendar3" in content
    assert "Shopping list" not in content
    assert 'aria-label="Edit list"' in content
    assert 'aria-label="Delete list"' in content


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


@pytest.mark.django_db
def test_list_overview_offers_edit_and_modal_delete_actions(client, user, shopping_list):
    client.force_login(user)

    response = client.get(reverse("shopping:list"))

    content = response.content.decode()
    assert 'class="card-body position-relative"' in content
    assert 'stretched-link text-decoration-none link-dark' in content
    assert f'{reverse("shopping:update", args=[shopping_list.pk])}?return_to=overview' in content
    assert f'data-bs-target="#delete-list-modal-{shopping_list.pk}"' in content


@pytest.mark.django_db
def test_edit_from_overview_returns_to_list_overview(client, user, shopping_list):
    client.force_login(user)

    response = client.post(
        f'{reverse("shopping:update", args=[shopping_list.pk])}?return_to=overview',
        {"title": "Umbenannte Liste", "date": "2026-10-30"},
    )

    assert response.url == reverse("shopping:list")


@pytest.mark.django_db
def test_edit_from_detail_returns_to_list_detail(client, user, shopping_list):
    client.force_login(user)

    response = client.post(
        reverse("shopping:update", args=[shopping_list.pk]),
        {"title": "Umbenannte Liste", "date": "2026-10-30"},
    )

    assert response.url == reverse("shopping:detail", args=[shopping_list.pk])


@pytest.mark.django_db
def test_edit_from_overview_cancels_to_list_overview(client, user, shopping_list):
    client.force_login(user)

    response = client.get(f'{reverse("shopping:update", args=[shopping_list.pk])}?return_to=overview')

    assert f'<a class="btn btn-outline-secondary" href="{reverse("shopping:list")}">Cancel</a>' in response.content.decode()


@pytest.mark.django_db
def test_edit_from_detail_cancels_to_list_detail(client, user, shopping_list):
    client.force_login(user)

    response = client.get(reverse("shopping:update", args=[shopping_list.pk]))

    assert f'<a class="btn btn-outline-secondary" href="{reverse("shopping:detail", args=[shopping_list.pk])}">Cancel</a>' in response.content.decode()


@pytest.mark.django_db
def test_json_import_creates_lists_and_items_for_current_user(client, user):
    client.force_login(user)

    response = client.post(
        reverse("shopping:import-json"),
        {
            "json_data": """{
                \"lists\": [{
                    \"title\": \"Tofu pan\",
                    \"date\": \"2026-10-31\",
                    \"items\": [{\"name\": \"Tofu\", \"quantity\": \"400 g\"}]
                }]
            }"""
        },
    )

    assert response.status_code == 302
    imported_list = ShoppingList.objects.get(user=user, title="Tofu pan")
    assert imported_list.date == date(2026, 10, 31)
    assert list(imported_list.items.values_list("name", "quantity")) == [("Tofu", "400 g")]


@pytest.mark.django_db
def test_json_import_rejects_invalid_json_without_creating_a_list(client, user):
    client.force_login(user)

    response = client.post(reverse("shopping:import-json"), {"json_data": "not json"})

    assert response.status_code == 200
    assert ShoppingList.objects.filter(user=user).count() == 0
    assert "invalid-feedback" in response.content.decode()
