import re

import pytest
from playwright.sync_api import expect


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_user_can_create_and_check_an_item(authenticated_page):
    page = authenticated_page

    page.get_by_role("link", name="Neue Liste").click()
    page.locator("input[name=title]").fill("Asiatische Erdnuss-Tofu-Pfanne")
    page.locator("input[name=date]").fill("2026-10-30")
    page.get_by_role("button", name="Speichern").click()

    page.get_by_label("Artikel").fill("Naturtofu")
    page.get_by_label("Menge").fill("400 g")
    page.get_by_role("button", name="Hinzufügen").click()

    item = page.locator(".shopping-item", has_text="Naturtofu")
    item.wait_for()
    item.get_by_role("button", name="Erledigt umschalten").click()
    expect(item).to_have_class(re.compile(r".*\bchecked\b.*"))


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_user_cannot_see_another_users_list(authenticated_page, other_user):
    from shopping.models import ShoppingList

    ShoppingList.objects.create(user=other_user, title="Private Liste")
    page = authenticated_page
    expect(page.get_by_text("Private Liste")).to_have_count(0)


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_user_can_hide_and_reset_completed_items(authenticated_page, user):
    from shopping.models import ShoppingItem, ShoppingList

    shopping_list = ShoppingList.objects.create(user=user, title="Wocheneinkauf")
    completed = ShoppingItem.objects.create(shopping_list=shopping_list, name="Tofu", checked=True)
    ShoppingItem.objects.create(shopping_list=shopping_list, name="Reis")
    page = authenticated_page
    page.route("**/easylist.css", lambda route: route.abort())
    page.goto(f"{page.url.rstrip('/')}/listen/{shopping_list.pk}/")

    completed_item = page.locator(f'.shopping-item[data-item-id="{completed.pk}"]')
    page.get_by_role("button", name="Erledigte ausblenden").click()
    expect(completed_item).to_be_hidden()

    page.get_by_role("button", name="Alle als nicht erledigt markieren").click()
    expect(completed_item).to_be_visible()
    expect(completed_item).not_to_have_class(re.compile(r".*\bchecked\b.*"))


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_user_can_edit_a_list_from_the_overview(authenticated_page, user):
    from shopping.models import ShoppingList

    shopping_list = ShoppingList.objects.create(user=user, title="Alter Titel")
    page = authenticated_page
    page.reload()
    card = page.locator(".list-card", has_text="Alter Titel")

    card.get_by_role("link", name="Bearbeiten").click()
    page.locator("input[name=title]").fill("Neuer Titel")
    page.get_by_role("button", name="Speichern").click()
    expect(page.get_by_role("heading", name="Meine Listen")).to_be_visible()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_user_can_edit_a_list_from_its_detail_page(authenticated_page, user):
    from shopping.models import ShoppingList

    shopping_list = ShoppingList.objects.create(user=user, title="Alter Titel")
    page = authenticated_page
    page.goto(f"{page.url.rstrip('/')}/listen/{shopping_list.pk}/")

    page.get_by_role("link", name="Bearbeiten").click()
    page.locator("input[name=title]").fill("Neuer Titel")
    page.get_by_role("button", name="Speichern").click()

    expect(page.get_by_role("heading", name="Neuer Titel")).to_be_visible()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_user_can_delete_a_list_from_the_overview_modal(authenticated_page, user):
    from shopping.models import ShoppingList

    ShoppingList.objects.create(user=user, title="Zu löschen")
    page = authenticated_page
    page.reload()

    card = page.locator(".list-card", has_text="Zu löschen")
    card.get_by_role("button", name="Liste löschen").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    dialog.get_by_role("button", name="Endgültig löschen").click()
    expect(page.get_by_text("Zu löschen")).to_have_count(0)


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_user_can_reorder_items_with_drag_and_drop(authenticated_page, user):
    from shopping.models import ShoppingItem, ShoppingList

    shopping_list = ShoppingList.objects.create(user=user, title="Wocheneinkauf")
    tofu = ShoppingItem.objects.create(shopping_list=shopping_list, name="Tofu", position=1)
    rice = ShoppingItem.objects.create(shopping_list=shopping_list, name="Reis", position=2)
    page = authenticated_page
    page.goto(f"{page.url.rstrip('/')}/listen/{shopping_list.pk}/")

    tofu_handle = page.locator(f'.shopping-item[data-item-id="{tofu.pk}"]').get_by_role("button", name="Verschieben")
    rice_handle = page.locator(f'.shopping-item[data-item-id="{rice.pk}"]').get_by_role("button", name="Verschieben")
    with page.expect_response(lambda response: "/reihenfolge/" in response.url and response.request.method == "POST"):
        tofu_handle.drag_to(rice_handle)
    page.reload()

    item_names = page.locator(".shopping-item .item-name").all_text_contents()
    assert item_names == ["Reis", "Tofu"]
