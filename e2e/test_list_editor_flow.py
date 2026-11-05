import re

import pytest
from playwright.sync_api import expect

from easy_kitchen.models import ShoppingItem, ShoppingList


def wait_for_editor_swap(page):
    page.wait_for_function("!document.querySelector('.htmx-settling')")
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("width", [1280, 390])
def test_list_editor_draft_cancel_save_and_shopping_controls(authenticated_page, user, live_server, width):
    shopping_list = ShoppingList.objects.create(user=user, title="Market")
    onion = ShoppingItem.objects.create(shopping_list=shopping_list, name="Onion", quantity="1", position=1, checked=True)
    ShoppingItem.objects.create(shopping_list=shopping_list, name="Carrot", position=2)
    page = authenticated_page
    page.set_viewport_size({"width": width, "height": 844})
    detail = f"{live_server.url}/lists/{shopping_list.pk}/"
    page.goto(detail)
    page.evaluate("window.listEditorSentinel = true")
    expect(page.get_by_role("button", name="Edit", exact=True)).to_have_count(0)
    expect(page.get_by_role("button", name="Delete list", exact=True)).to_have_count(0)
    page.get_by_role("link", name="Edit list", exact=True).click()
    expect(page).to_have_url(detail + "edit/")
    wait_for_editor_swap(page)
    assert page.evaluate("window.scrollY") == 0
    page.get_by_label("Title", exact=True).fill("Discarded title")
    rows = page.locator('[data-editor-lines="items"] .editor-line:not([hidden])')
    rows.first.get_by_role("button", name="Remove item", exact=True).click()
    page.get_by_role("link", name="Cancel", exact=True).first.click()
    expect(page).to_have_url(detail)
    wait_for_editor_swap(page)
    assert page.evaluate("window.scrollY") == 0
    assert ShoppingList.objects.get(pk=shopping_list.pk).title == "Market"
    assert shopping_list.items.count() == 2
    page.get_by_role("link", name="Edit list", exact=True).click()
    page.get_by_label("Title", exact=True).fill("Weekly market")
    page.get_by_label("Date", exact=True).fill("2026-11-12")
    page.locator(".list-icon-choice").filter(has=page.get_by_role("radio", name="Flower", exact=True)).click()
    expect(page.get_by_role("radio", name="Flower", exact=True)).to_be_checked()
    rows.first.get_by_label("Item", exact=True).fill("Red onion")
    rows.first.get_by_label("Quantity", exact=True).fill("2")
    rows.nth(1).get_by_role("button", name="Remove item", exact=True).click()
    page.get_by_role("button", name="Add item", exact=True).click()
    rows.last.get_by_label("Item", exact=True).fill("Salt")
    rows.last.get_by_label("Quantity", exact=True).fill("1 tsp")
    rows.last.get_by_role("button", name="Move up", exact=True).click()
    assert shopping_list.items.get(pk=onion.pk).name == "Onion"
    expect(page.locator(".list-editor-footer")).to_have_css("position", "sticky")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.get_by_role("button", name="Save", exact=True).first.click()
    expect(page).to_have_url(detail)
    expect(page.get_by_role("heading", name="Weekly market", exact=True)).to_be_visible()
    assert page.evaluate("window.listEditorSentinel") is True
    assert list(shopping_list.items.values_list("name", "quantity")) == [("Salt", "1 tsp"), ("Red onion", "2")]
    onion.refresh_from_db()
    assert onion.checked
    shopping_list.refresh_from_db()
    assert shopping_list.date.isoformat() == "2026-11-12" and shopping_list.icon == "flower"
    page.get_by_role("button", name="Hide completed", exact=True).click()
    expect(page.locator(".shopping-item", has_text="Red onion")).to_be_hidden()
    page.get_by_role("button", name="Show completed", exact=True).click()
    page.locator(".shopping-item", has_text="Red onion").get_by_role("button", name="Toggle completed", exact=True).click()
    expect(page.locator(".shopping-item", has_text="Red onion")).not_to_have_class(re.compile(r"checked"))
    page.get_by_role("combobox", name="Item", exact=True).fill("Bread")
    page.get_by_role("button", name="Add", exact=True).click()
    expect(page.locator(".shopping-item", has_text="Bread")).to_be_visible()
    page.get_by_role("link", name="Edit list", exact=True).click()
    expect(page).to_have_url(detail + "edit/")
    page.go_back()
    expect(page).to_have_url(detail)
    expect(page.get_by_role("button", name="Hide completed", exact=True)).to_be_visible()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_list_editor_validation_and_delete_confirmation(authenticated_page, user, live_server):
    shopping_list = ShoppingList.objects.create(user=user, title="Market")
    ShoppingItem.objects.create(shopping_list=shopping_list, name="Onion")
    page = authenticated_page
    detail = f"{live_server.url}/lists/{shopping_list.pk}/"
    page.goto(detail + "edit/")
    page.get_by_label("Title", exact=True).fill("")
    page.locator("#list-editor-form").evaluate("form => { form.noValidate = true; }")
    page.get_by_role("button", name="Save", exact=True).first.click()
    expect(page.get_by_role("alert")).to_contain_text("Your changes have not been saved.")
    expect(page.get_by_label("Item", exact=True)).to_have_value("Onion")
    assert ShoppingList.objects.get(pk=shopping_list.pk).title == "Market"
    page.get_by_label("Title", exact=True).fill("Unsaved title")
    page.get_by_role("button", name="Delete list", exact=True).click()
    modal = page.get_by_role("dialog", name="Delete list?", exact=True)
    expect(modal).to_be_visible()
    modal.get_by_role("button", name="Cancel", exact=True).click()
    expect(modal).to_be_hidden()
    assert ShoppingList.objects.filter(pk=shopping_list.pk).exists()
    page.get_by_role("button", name="Delete list", exact=True).click()
    modal.get_by_role("button", name="Delete permanently", exact=True).click()
    expect(page).to_have_url(f"{live_server.url}/lists/")
    assert not ShoppingList.objects.filter(pk=shopping_list.pk).exists()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("width", [1280, 390])
@pytest.mark.parametrize("action", ["save", "cancel"])
def test_list_editor_preserves_scrolled_viewport(authenticated_page, user, live_server, width, action):
    shopping_list = ShoppingList.objects.create(user=user, title="Market")
    for index in range(16):
        ShoppingItem.objects.create(shopping_list=shopping_list, name=f"Article {index}", position=index)
    page = authenticated_page
    page.set_viewport_size({"width": width, "height": 844})
    detail = f"{live_server.url}/lists/{shopping_list.pk}/"
    page.goto(detail)
    page.evaluate("window.scrollTo({top: 80, behavior: 'instant'})")
    before = page.evaluate("window.scrollY")
    page.get_by_role("link", name="Edit list", exact=True).click()
    expect(page).to_have_url(detail + "edit/")
    wait_for_editor_swap(page)
    assert abs(page.evaluate("window.scrollY") - before) < 1
    if action == "save":
        page.get_by_role("button", name="Save", exact=True).first.click()
    else:
        page.get_by_role("link", name="Cancel", exact=True).first.click()
    expect(page).to_have_url(detail)
    wait_for_editor_swap(page)
    assert abs(page.evaluate("window.scrollY") - before) < 1
