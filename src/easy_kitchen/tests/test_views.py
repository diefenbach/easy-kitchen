import json

import pytest
from django.test import Client
from django.urls import reverse
from django.utils.formats import date_format
from datetime import date
from easy_kitchen.models import ShoppingItem, ShoppingList


@pytest.mark.django_db
def test_pages_show_the_wordmark_logo(client, user):
    client.force_login(user)
    content = client.get(reverse("easy_kitchen:home")).content.decode()
    assert "easy_kitchen/logo.png" in content
    assert ">Easy Kitchen</span>" in content
    assert 'aria-label="Easy Kitchen"' in content


@pytest.mark.django_db
def test_home_shows_the_three_newest_lists_and_recipes(client, user, other_user):
    from easy_kitchen.models import Recipe

    client.force_login(user)
    oldest_list = ShoppingList.objects.create(user=user, title="Oldest list")
    ShoppingList.objects.create(user=user, title="Second list")
    ShoppingList.objects.create(user=user, title="Third list")
    newest_list = ShoppingList.objects.create(user=user, title="Newest list")
    for position, name in enumerate(["Apples", "Bread", "Milk", "Cheese", "Honey"], start=1):
        ShoppingItem.objects.create(shopping_list=newest_list, name=name, quantity=f"{position}00 g", position=position)
    ShoppingList.objects.create(user=other_user, title="Foreign list")
    Recipe.objects.create(user=user, title="Oldest recipe")
    Recipe.objects.create(user=user, title="Second recipe")
    Recipe.objects.create(user=user, title="Third recipe")
    newest_recipe = Recipe.objects.create(user=user, title="Newest recipe")
    Recipe.objects.create(user=other_user, title="Foreign recipe")

    response = client.get(reverse("easy_kitchen:home"))

    assert response.status_code == 200
    content = response.content.decode()
    assert reverse("easy_kitchen:list") == "/lists/"
    for title in ("Newest list", "Third list", "Second list", "Newest recipe", "Third recipe", "Second recipe"):
        assert title in content
    assert "Oldest list" not in content
    assert "Oldest recipe" not in content
    assert "Foreign list" not in content
    assert "Foreign recipe" not in content
    assert reverse("easy_kitchen:detail", args=[newest_list.pk]) in content
    assert reverse("easy_kitchen:detail", args=[oldest_list.pk]) not in content
    assert reverse("easy_kitchen:recipe-detail", args=[newest_recipe.pk]) in content
    assert "Apples" in content and "100 g" in content
    assert "Cheese" in content and "400 g" in content
    assert "Honey" not in content
    assert "5 items" in content
    assert 'class="card-header"' in content
    assert 'class="list-preview"' in content
    assert 'class="card-footer list-card-date"' in content
    assert "bi-calendar3" in content
    assert date_format(newest_list.date, "j. F Y") in content
    assert "Sun," not in content
    assert 'class="btn btn-sm btn-outline-secondary is-active" href="/" aria-label="Overview"' in content
    assert 'class="btn btn-sm btn-outline-secondary dropdown-toggle"' in content
    assert 'aria-label="kai"' in content
    assert 'class="d-none d-md-inline">kai</span>' in content
    assert 'class="dropdown-item"' in content
    assert 'class="btn btn-sm btn-outline-secondary" href="/lists/" aria-label="Shopping lists"' in content
    assert "See all lists" in content
    assert "See all recipes" in content
    recipes_heading = '<h2 class="h3 mb-0">Recipes</h2>'
    assert content.index('href="/lists/new/"') < content.index(recipes_heading)
    assert content.index(recipes_heading) < content.index('href="/recipes/new/"')
    assert 'aria-label="New list"' in content
    assert 'aria-label="New recipe"' in content
    assert 'data-edit-toggle aria-pressed' not in content
    assert "edit-only" not in content

    lists = client.get(reverse("easy_kitchen:list")).content.decode()
    assert "Oldest list" in lists
    assert 'class="btn btn-sm btn-outline-secondary is-active" href="/lists/" aria-label="Shopping lists"' in lists


@pytest.mark.django_db
def test_login_lands_on_the_home_page(client, user):
    response = client.post(reverse("login"), {"username": "kai", "password": "test-password"})

    assert response.status_code == 302
    assert response.url == reverse("easy_kitchen:home")


@pytest.mark.django_db
def test_lists_are_scoped_to_current_user(client, user, other_user):
    own = ShoppingList.objects.create(user=user, title="Meine")
    ShoppingList.objects.create(user=other_user, title="Fremde")
    client.force_login(user)
    response = client.get(reverse("easy_kitchen:list"))
    assert response.status_code == 200
    assert "Meine" in response.content.decode()
    assert "Fremde" not in response.content.decode()
    assert client.get(reverse("easy_kitchen:detail", args=[own.pk])).status_code == 200


@pytest.mark.django_db
def test_user_cannot_access_other_list(client, user, other_user):
    other_list = ShoppingList.objects.create(user=other_user, title="Privat")
    client.force_login(user)
    assert client.get(reverse("easy_kitchen:detail", args=[other_list.pk])).status_code == 404


@pytest.mark.django_db
def test_item_name_suggests_saved_articles(client, user, shopping_list):
    from easy_kitchen.services import create_item

    client.force_login(user)
    create_item(shopping_list, name="Hafermilch")
    detail = client.get(reverse("easy_kitchen:detail", args=[shopping_list.pk])).content.decode()
    assert 'class="article-field"' in detail
    assert 'class="article-suggestions"' in detail
    assert 'list="articles"' not in detail
    assert '<option value="Hafermilch"></option>' in detail

    response = client.post(
        reverse("easy_kitchen:item-create", args=[shopping_list.pk]),
        {"name": "Brokkoli", "quantity": "1"},
        HTTP_HX_REQUEST="true",
    )
    suggestions = response.content.decode()
    assert 'id="articles"' in suggestions
    assert 'hx-swap-oob="outerHTML"' in suggestions
    assert '<option value="Hafermilch"></option>' in suggestions
    assert '<option value="Brokkoli"></option>' in suggestions


@pytest.mark.django_db
def test_articles_can_be_managed_without_changing_list_items(client, user, other_user, shopping_list):
    from easy_kitchen.models import Article
    from easy_kitchen.services import create_item

    client.force_login(user)
    create_item(shopping_list, name="Milch", quantity="1 l")
    create_item(shopping_list, name="Brot")
    milk = Article.objects.get(user=user, name="Milch")
    bread = Article.objects.get(user=user, name="Brot")

    renamed = client.post(reverse("easy_kitchen:article-update", args=[milk.pk]), {"name": "Hafermilch"})
    assert renamed.status_code == 302
    milk.refresh_from_db()
    assert milk.name == "Hafermilch"
    assert shopping_list.items.get(quantity="1 l").name == "Milch"

    duplicate = client.post(reverse("easy_kitchen:article-update", args=[milk.pk]), {"name": " brot "})
    assert duplicate.status_code == 422
    assert "already exists" in duplicate.content.decode()
    milk.refresh_from_db()
    assert milk.name == "Hafermilch"

    overview = client.get(reverse("easy_kitchen:articles"))
    assert overview.status_code == 200
    content = overview.content.decode()
    assert ">Edit articles</span>" in content
    assert 'aria-label="Save"' in content
    assert 'class="bi bi-check-lg"' in content
    assert 'aria-label="Delete"' in content
    assert 'data-edit-toggle aria-pressed' not in content
    assert 'class="bi bi-trash"' in content
    assert ">Save</button>" not in content
    assert ">Delete</button>" not in content
    created = client.post(reverse("easy_kitchen:articles"), {"name": "Reis"})
    assert created.status_code == 302
    assert Article.objects.filter(user=user, name="Reis").exists()

    client.post(reverse("easy_kitchen:article-delete", args=[bread.pk]))
    assert not Article.objects.filter(pk=bread.pk).exists()
    assert shopping_list.items.filter(name="Brot").exists()

    client.force_login(other_user)
    hidden = client.get(reverse("easy_kitchen:articles")).content.decode()
    assert "Hafermilch" not in hidden
    assert client.post(reverse("easy_kitchen:article-update", args=[milk.pk]), {"name": "Geheim"}).status_code == 404
    assert client.post(reverse("easy_kitchen:article-delete", args=[milk.pk])).status_code == 404


@pytest.mark.django_db
def test_articles_return_to_the_page_they_were_opened_from(client, user, other_user, shopping_list):
    client.force_login(user)
    detail_url = reverse("easy_kitchen:detail", args=[shopping_list.pk])
    articles_url = reverse("easy_kitchen:articles")

    overview = client.get(reverse("easy_kitchen:list")).content.decode()
    assert f'href="{articles_url}"' in overview
    assert f"{articles_url}?list=" not in overview
    opened_from_overview = client.get(articles_url).content.decode()
    assert f'href="{reverse("easy_kitchen:list")}"' in opened_from_overview
    assert "Shopping lists" in opened_from_overview

    detail = client.get(detail_url).content.decode()
    assert f'href="{articles_url}?list={shopping_list.pk}"' in detail
    opened_from_list = client.get(f"{articles_url}?list={shopping_list.pk}").content.decode()
    assert f'href="{detail_url}"' in opened_from_list
    assert shopping_list.title in opened_from_list

    other_list = ShoppingList.objects.create(user=other_user, title="Privat")
    foreign = client.get(f"{articles_url}?list={other_list.pk}").content.decode()
    assert reverse("easy_kitchen:detail", args=[other_list.pk]) not in foreign
    assert "Privat" not in foreign

    created = client.post(articles_url, {"name": "Reis", "return_list": shopping_list.pk})
    assert created.status_code == 302
    assert created["Location"] == f"{articles_url}?list={shopping_list.pk}"


@pytest.mark.django_db
def test_only_identical_counts_are_added_when_the_same_item_is_posted(client, user, shopping_list):
    client.force_login(user)
    url = reverse("easy_kitchen:item-create", args=[shopping_list.pk])
    client.post(url, {"name": "Äpfel", "quantity": "2 Stück"}, HTTP_HX_REQUEST="true")
    response = client.post(url, {"name": "Äpfel", "quantity": "2 Stück"}, HTTP_HX_REQUEST="true")

    assert response.status_code == 200
    assert "4 Stück" in response.content.decode()

    response = client.post(url, {"name": "Äpfel", "quantity": "4 Teile"}, HTTP_HX_REQUEST="true")
    assert "4 Stück, 4 Teile" in response.content.decode()
    assert ShoppingItem.objects.get(shopping_list=shopping_list).quantity == "4 Stück, 4 Teile"


@pytest.mark.django_db
def test_adding_the_same_item_updates_the_existing_row(client, user, shopping_list):
    client.force_login(user)
    create_url = reverse("easy_kitchen:item-create", args=[shopping_list.pk])
    client.post(create_url, {"name": "Milch", "quantity": "1 l"}, HTTP_HX_REQUEST="true")
    response = client.post(create_url, {"name": "Milch", "quantity": "500 ml"}, HTTP_HX_REQUEST="true")

    item = ShoppingItem.objects.get(shopping_list=shopping_list)
    assert response.status_code == 200
    assert response["HX-Retarget"] == f'.shopping-item[data-item-id="{item.id}"]'
    assert response["HX-Reswap"] == "outerHTML"
    content = response.content.decode()
    assert "1 l, 500 ml" in content
    assert f'id="delete-item-modal-{item.id}"' not in content


@pytest.mark.django_db
def test_htmx_item_create_and_toggle(client, user, shopping_list):
    client.force_login(user)
    response = client.post(reverse("easy_kitchen:item-create", args=[shopping_list.pk]), {"name": "Tofu", "quantity": "400 g"}, HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    item = ShoppingItem.objects.get(shopping_list=shopping_list)
    response = client.post(reverse("easy_kitchen:item-toggle", args=[shopping_list.pk, item.pk]), HTTP_HX_REQUEST="true")
    item.refresh_from_db()
    assert item.checked is True
    assert "☑" in response.content.decode()


@pytest.mark.django_db
def test_item_toggle_requires_and_accepts_csrf_token(client, user, shopping_list):
    item = ShoppingItem.objects.create(shopping_list=shopping_list, name="Tofu")
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(user)
    detail_response = csrf_client.get(reverse("easy_kitchen:detail", args=[shopping_list.pk]))
    assert 'src="/static/easy_kitchen/easykitchen.js"' in detail_response.content.decode()
    assert csrf_client.post(
        reverse("easy_kitchen:item-toggle", args=[shopping_list.pk, item.pk]),
        HTTP_HX_REQUEST="true",
    ).status_code == 403
    token = csrf_client.cookies["csrftoken"].value
    response = csrf_client.post(
        reverse("easy_kitchen:item-toggle", args=[shopping_list.pk, item.pk]),
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

    response = client.get(reverse("easy_kitchen:detail", args=[shopping_list.pk]))

    content = response.content.decode()
    assert 'data-bs-target="#delete-list-modal"' in content
    assert 'data-bs-target="#delete-item-modal-' in content
    assert 'role="group" aria-label="Item actions"' in content
    assert 'class="drag-handle edit-only' in content
    assert 'class="btn-group edit-only" role="group" aria-label="Item actions"' in content
    assert "hx-confirm" not in content


@pytest.mark.django_db
def test_list_icon_defaults_to_a_basket_and_can_be_changed(client, user):
    client.force_login(user)

    created = client.post(
        reverse("easy_kitchen:create"),
        {"title": "Market", "date": "2026-11-01"},
    )
    shopping_list = ShoppingList.objects.get(user=user, title="Market")
    assert created.status_code == 302
    assert shopping_list.icon == ShoppingList.Icon.BASKET

    overview = client.get(reverse("easy_kitchen:list")).content.decode()
    assert "bi-basket" in overview
    assert "list-icon-basket" in overview
    assert "list-accent-basket" in overview
    home = client.get(reverse("easy_kitchen:home")).content.decode()
    assert "bi-basket" in home
    assert "list-accent-basket" in home

    form = client.get(reverse("easy_kitchen:update", args=[shopping_list.pk])).content.decode()
    for icon_class in ShoppingList.ICON_CLASSES.values():
        assert icon_class in form

    updated = client.post(
        reverse("easy_kitchen:update", args=[shopping_list.pk]),
        {"title": "Market", "date": "2026-11-01", "icon": "flower"},
    )
    assert updated.status_code == 302
    shopping_list.refresh_from_db()
    assert shopping_list.icon == ShoppingList.Icon.FLOWER
    detail = client.get(reverse("easy_kitchen:detail", args=[shopping_list.pk])).content.decode()
    assert "bi-flower1" in detail
    assert "list-icon-flower" in detail
    assert "list-accent-flower" in detail
    assert 'class="card-footer list-card-date"' in detail
    overview = client.get(reverse("easy_kitchen:list")).content.decode()
    assert "list-accent-flower" in overview

    rejected = client.post(
        reverse("easy_kitchen:update", args=[shopping_list.pk]),
        {"title": "Market", "date": "2026-11-01", "icon": "pasta"},
    )
    assert rejected.status_code == 200
    shopping_list.refresh_from_db()
    assert shopping_list.icon == ShoppingList.Icon.FLOWER


@pytest.mark.django_db
def test_list_detail_uses_a_minimal_icon_header(client, user, shopping_list):
    client.force_login(user)

    response = client.get(reverse("easy_kitchen:detail", args=[shopping_list.pk]))

    content = response.content.decode()
    assert 'class="btn btn-outline-secondary btn-sm list-back-button mb-3"' in content
    assert f'class="card list-accent list-accent-{shopping_list.icon} mb-4"' in content
    assert 'class="card-footer list-card-date"' in content
    assert date_format(shopping_list.date, "j. F Y") in content
    assert "Sun," not in content
    assert "bi-arrow-left" in content
    assert "bi-calendar3" in content
    assert ">Shopping lists</span>" in content
    assert 'aria-label="Edit list"' in content
    assert 'aria-label="Delete list"' in content
    assert "data-edit-toggle" in content
    assert 'src="/static/easy_kitchen/list-detail.js"' in content
    assert f'data-hide-completed-url="/lists/{shopping_list.pk}/hide-completed/"' in content


@pytest.mark.django_db
def test_hide_completed_preference_is_stored_on_the_list(client, user, shopping_list):
    ShoppingItem.objects.create(shopping_list=shopping_list, name="Tofu", checked=True)
    client.force_login(user)

    save = client.post(
        reverse("easy_kitchen:list-hide-completed", args=[shopping_list.pk]),
        json.dumps({"hide": True}),
        content_type="application/json",
    )
    assert save.status_code == 204
    shopping_list.refresh_from_db()
    assert shopping_list.hide_completed_items is True

    content = client.get(reverse("easy_kitchen:detail", args=[shopping_list.pk])).content.decode()
    assert 'id="items" class="hide-completed"' in content
    assert "Show completed" in content


@pytest.mark.django_db
def test_list_detail_completed_item_actions_keep_visible_labels(client, user, shopping_list):
    client.force_login(user)

    content = client.get(reverse("easy_kitchen:detail", args=[shopping_list.pk])).content.decode()

    assert '<span class="btn-label">Hide completed</span>' in content
    assert 'd-none d-md-inline">Hide completed' not in content
    assert "Mark all as not completed" not in content


@pytest.mark.django_db
def test_list_detail_shows_delete_completed_when_items_are_checked(client, user, shopping_list):
    ShoppingItem.objects.create(shopping_list=shopping_list, name="Tofu", checked=True)
    client.force_login(user)

    content = client.get(reverse("easy_kitchen:detail", args=[shopping_list.pk])).content.decode()

    assert 'aria-label="Delete completed"' in content
    assert "Delete completed items?" in content
    assert 'id="delete-completed-modal"' in content


@pytest.mark.django_db
def test_list_detail_keeps_delete_completed_disabled_without_checked_items(client, user, shopping_list):
    ShoppingItem.objects.create(shopping_list=shopping_list, name="Tofu")
    client.force_login(user)

    content = client.get(reverse("easy_kitchen:detail", args=[shopping_list.pk])).content.decode()

    assert 'id="delete-completed-trigger"' in content
    assert 'id="delete-completed-trigger"' in content and " disabled" in content.split('id="delete-completed-trigger"', 1)[1].split(">", 1)[0]
    assert 'id="delete-completed-modal"' in content


@pytest.mark.django_db
def test_list_detail_item_row_actions_are_icon_only(client, user, shopping_list):
    ShoppingItem.objects.create(shopping_list=shopping_list, name="Tofu")
    client.force_login(user)

    content = client.get(reverse("easy_kitchen:detail", args=[shopping_list.pk])).content.decode()

    assert 'aria-label="Edit item"' in content
    assert 'aria-label="Delete item"' in content
    assert 'd-none d-md-inline">Edit item' not in content
    assert 'd-none d-md-inline">Delete item' not in content


@pytest.mark.django_db
def test_item_edit_form_vertically_centers_save_button(client, user, shopping_list):
    item = ShoppingItem.objects.create(shopping_list=shopping_list, name="Tofu", quantity="400 g")
    client.force_login(user)

    content = client.get(reverse("easy_kitchen:item-update", args=[shopping_list.pk, item.pk])).content.decode()

    assert 'class="card-body py-2 px-3 row g-2 align-items-center"' in content


@pytest.mark.django_db
def test_edit_list_prefills_html_date_input(client, user, shopping_list):
    shopping_list.date = date(2026, 10, 30)
    shopping_list.save()
    client.force_login(user)

    response = client.get(reverse("easy_kitchen:update", args=[shopping_list.pk]))

    assert '<input type="date" name="date" value="2026-10-30"' in response.content.decode()


@pytest.mark.django_db
def test_delete_completed_items_removes_only_checked_items(client, user, shopping_list):
    completed = ShoppingItem.objects.create(shopping_list=shopping_list, name="Tofu", checked=True)
    open_item = ShoppingItem.objects.create(shopping_list=shopping_list, name="Reis")
    client.force_login(user)

    response = client.post(reverse("easy_kitchen:items-delete-completed", args=[shopping_list.pk]), follow=True)

    assert response.status_code == 200
    assert not ShoppingItem.objects.filter(pk=completed.pk).exists()
    assert ShoppingItem.objects.filter(pk=open_item.pk).exists()
    assert "Deleted one completed item." in response.content.decode()


@pytest.mark.django_db
def test_list_overview_offers_edit_and_modal_delete_actions(client, user, shopping_list):
    client.force_login(user)

    response = client.get(reverse("easy_kitchen:list"))

    content = response.content.decode()
    assert 'class="card h-100 list-card list-accent list-accent-basket position-relative"' in content
    assert 'class="card-header"' in content
    assert 'stretched-link text-decoration-none link-dark' in content
    assert f'{reverse("easy_kitchen:update", args=[shopping_list.pk])}?return_to=overview' in content
    assert f'data-bs-target="#delete-list-modal-{shopping_list.pk}"' in content
    assert 'data-edit-toggle' in content
    assert 'data-card-reorder' in content
    assert 'aria-label="Move"' in content
    assert ">Move</span>" not in content
    assert 'class="card-footer bg-white d-flex flex-nowrap align-items-center gap-2 edit-only position-relative z-2"' in content
    assert 'class="dropdown-item" href="/import/" aria-label="Import JSON"' in content
    assert 'class="dropdown-item" href="/export/" aria-label="Export JSON"' in content
    assert 'class="btn btn-outline-secondary" aria-label="Import JSON"' not in content
    assert 'class="btn btn-outline-secondary" aria-label="Export JSON"' not in content
    assert 'bi-plus-lg' in content
    assert 'd-none d-md-inline">New list</span>' in content


@pytest.mark.django_db
def test_list_overview_reorder_keeps_other_users_lists(client, user, other_user):
    first = ShoppingList.objects.create(user=user, title="First")
    second = ShoppingList.objects.create(user=user, title="Second")
    foreign = ShoppingList.objects.create(user=other_user, title="Foreign")
    client.force_login(user)

    response = client.post(
        reverse("easy_kitchen:list-reorder"),
        json.dumps({"list_ids": [first.pk, second.pk, foreign.pk]}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert list(user.shopping_lists.values_list("title", flat=True)) == ["Second", "First"]
    kept = client.post(
        reverse("easy_kitchen:list-reorder"),
        json.dumps({"list_ids": [first.pk, second.pk]}),
        content_type="application/json",
    )
    assert kept.status_code == 204
    assert list(user.shopping_lists.values_list("title", flat=True)) == ["First", "Second"]


@pytest.mark.django_db
def test_edit_from_overview_returns_to_list_overview(client, user, shopping_list):
    client.force_login(user)

    response = client.post(
        f'{reverse("easy_kitchen:update", args=[shopping_list.pk])}?return_to=overview',
        {"title": "Umbenannte Liste", "date": "2026-10-30"},
    )

    assert response.url == reverse("easy_kitchen:list")


@pytest.mark.django_db
def test_edit_from_detail_returns_to_list_detail(client, user, shopping_list):
    client.force_login(user)

    response = client.post(
        reverse("easy_kitchen:update", args=[shopping_list.pk]),
        {"title": "Umbenannte Liste", "date": "2026-10-30"},
    )

    assert response.url == reverse("easy_kitchen:detail", args=[shopping_list.pk])


@pytest.mark.django_db
def test_edit_from_overview_cancels_to_list_overview(client, user, shopping_list):
    client.force_login(user)

    response = client.get(f'{reverse("easy_kitchen:update", args=[shopping_list.pk])}?return_to=overview')

    content = response.content.decode()
    assert f'href="{reverse("easy_kitchen:list")}"' in content
    assert 'd-none d-md-inline">Cancel</span>' in content


@pytest.mark.django_db
def test_edit_from_detail_cancels_to_list_detail(client, user, shopping_list):
    client.force_login(user)

    response = client.get(reverse("easy_kitchen:update", args=[shopping_list.pk]))

    content = response.content.decode()
    assert f'href="{reverse("easy_kitchen:detail", args=[shopping_list.pk])}"' in content
    assert 'd-none d-md-inline">Cancel</span>' in content


@pytest.mark.django_db
def test_json_import_creates_lists_and_items_for_current_user(client, user):
    client.force_login(user)

    response = client.post(
        reverse("easy_kitchen:import-json"),
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
    assert response.url == reverse("easy_kitchen:list")
    imported_list = ShoppingList.objects.get(user=user, title="Tofu pan")
    assert imported_list.date == date(2026, 10, 31)
    assert list(imported_list.items.values_list("name", "quantity")) == [("Tofu", "400 g")]


@pytest.mark.django_db
def test_status_messages_are_marked_to_hide_after_three_seconds(client, user):
    client.force_login(user)

    response = client.post(
        reverse("easy_kitchen:import-json"),
        {
            "json_data": """{
                \"lists\": [{
                    \"title\": \"Tofu pan\",
                    \"date\": \"2026-10-31\",
                    \"items\": [{\"name\": \"Tofu\", \"quantity\": \"400 g\"}]
                }]
            }"""
        },
        follow=True,
    )

    content = response.content.decode()
    assert "Imported 1 shopping list." in content
    assert 'data-autohide="3000"' in content


@pytest.mark.django_db
def test_list_views_show_a_status_message_after_create_update_and_delete(client, user):
    client.force_login(user)

    created = client.post(
        reverse("easy_kitchen:create"),
        {"title": "Market", "date": "2026-11-01"},
        follow=True,
    )
    shopping_list = ShoppingList.objects.get(user=user, title="Market")
    assert "Shopping list created." in created.content.decode()
    assert 'data-autohide="3000"' in created.content.decode()

    updated = client.post(
        reverse("easy_kitchen:update", args=[shopping_list.pk]),
        {"title": "Market", "date": "2026-11-01"},
        follow=True,
    )
    assert "Shopping list updated." in updated.content.decode()

    deleted = client.post(reverse("easy_kitchen:delete", args=[shopping_list.pk]), follow=True)
    assert "Shopping list deleted." in deleted.content.decode()
    assert reverse("easy_kitchen:list") == deleted.request["PATH_INFO"]


@pytest.mark.django_db
def test_json_import_rejects_invalid_json_without_creating_a_list(client, user):
    client.force_login(user)

    response = client.post(reverse("easy_kitchen:import-json"), {"json_data": "not json"})

    assert response.status_code == 200
    assert ShoppingList.objects.filter(user=user).count() == 0
    assert "invalid-feedback" in response.content.decode()


@pytest.mark.django_db
def test_json_import_recognizes_a_recipe_without_a_wrapper(client, user):
    from easy_kitchen.models import Recipe

    client.force_login(user)

    response = client.post(
        reverse("easy_kitchen:import-json"),
        {"json_data": '[{"title": "Soup", "ingredients": [{"name": "Onion", "quantity": "1"}]}]'},
    )

    assert response.status_code == 302
    assert response.url == reverse("easy_kitchen:recipes")
    assert Recipe.objects.filter(user=user, title="Soup").exists()


@pytest.mark.django_db
def test_json_import_rejects_json_that_is_neither_list_nor_recipe(client, user):
    client.force_login(user)

    response = client.post(reverse("easy_kitchen:import-json"), {"json_data": '{"hello": 1}'})

    assert response.status_code == 200
    assert "Could not tell whether this is a shopping list or a recipe." in response.content.decode()


@pytest.mark.django_db
def test_export_page_lists_only_the_current_users_lists_and_recipes(client, user, other_user, shopping_list):
    from easy_kitchen.models import Recipe
    from easy_kitchen.services import create_recipe

    create_recipe(user, title="Pancakes")
    ShoppingList.objects.create(user=other_user, title="Foreign list")
    Recipe.objects.create(user=other_user, title="Foreign recipe")
    client.force_login(user)

    response = client.get(reverse("easy_kitchen:export-json"))

    content = response.content.decode()
    assert response.status_code == 200
    assert "Export JSON" in content
    assert "Wocheneinkauf" in content
    assert "Pancakes" in content
    assert "Foreign list" not in content
    assert "Foreign recipe" not in content


@pytest.mark.django_db
def test_export_downloads_selected_lists_and_recipes_as_importable_json(
    client, user, other_user, shopping_list
):
    from easy_kitchen.models import Recipe
    from easy_kitchen.services import create_item, create_recipe

    create_item(shopping_list, name="Milk", quantity="1 l")
    recipe = create_recipe(
        user,
        title="Soup",
        description="Weeknight",
        image_url="https://example.com/soup.jpg",
        calories=300,
        ingredients=[{"name": "Onion", "quantity": "1"}],
        steps=[{"text": "Simmer."}],
    )
    foreign_list = ShoppingList.objects.create(user=other_user, title="Foreign list")
    foreign_recipe = Recipe.objects.create(user=other_user, title="Foreign recipe")
    client.force_login(user)

    response = client.post(
        reverse("easy_kitchen:export-json"),
        {"lists": [shopping_list.pk, foreign_list.pk], "recipes": [recipe.pk, foreign_recipe.pk]},
    )

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/json")
    assert 'attachment; filename="easykitchen.json"' in response["Content-Disposition"]
    payload = json.loads(response.content)
    assert payload == {
        "lists": [
            {
                "title": "Wocheneinkauf",
                "icon": "basket",
                "date": shopping_list.date.isoformat(),
                "items": [{"name": "Milk", "quantity": "1 l", "checked": False}],
            }
        ],
        "recipes": [
            {
                "title": "Soup",
                "description": "Weeknight",
                "image_url": "https://example.com/soup.jpg",
                "calories": 300,
                "ingredients": [{"name": "Onion", "quantity": "1"}],
                "steps": [{"text": "Simmer."}],
            }
        ],
    }


@pytest.mark.django_db
def test_export_requires_at_least_one_selection(client, user, shopping_list):
    client.force_login(user)

    response = client.post(reverse("easy_kitchen:export-json"), {})

    assert response.status_code == 200
    assert "Choose at least one shopping list or recipe." in response.content.decode()
    assert response.get("Content-Disposition") is None
