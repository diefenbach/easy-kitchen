import pytest
from playwright.sync_api import expect

from easy_kitchen.models import Article, ShoppingItem, ShoppingList


pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


def open_list(page, user, live_server):
    shopping_list = ShoppingList.objects.create(user=user, title="Groceries")
    ShoppingItem.objects.create(shopping_list=shopping_list, name="Milk", checked=True)
    page.goto(f"{live_server.url}/lists/{shopping_list.pk}/")
    return shopping_list


def test_article_suggestions_support_keyboard_selection(authenticated_page, user, live_server):
    Article.objects.create(user=user, name="Avocado")
    Article.objects.create(user=user, name="Apple")
    page = authenticated_page
    open_list(page, user, live_server)
    name = page.get_by_role("combobox", name="Item")
    name.fill("Avo")
    name.press("ArrowDown")
    selected_id = name.get_attribute("aria-activedescendant")
    assert selected_id
    expect(page.locator(f"#{selected_id}")).to_have_attribute("aria-selected", "true")
    assert name.get_attribute("aria-controls")
    name.press("Enter")
    expect(name).to_have_value("Avocado")
    expect(name).to_have_attribute("aria-expanded", "false")
    expect(name).to_be_focused()
    name.fill("App")
    page.get_by_role("option", name="Apple", exact=True).focus()
    page.keyboard.press("Enter")
    expect(name).to_have_value("Apple")
    name.press("Escape")
    expect(name).to_have_attribute("aria-expanded", "false")


def test_item_dialog_stays_unique_and_uses_updated_name(authenticated_page, user, live_server):
    page = authenticated_page
    shopping_list = open_list(page, user, live_server)
    item = shopping_list.items.get()
    card = page.locator(f'.shopping-item[data-item-id="{item.pk}"]')
    for _ in range(2):
        card.get_by_role("button", name="Toggle completed", exact=True).click()
        page.wait_for_function("!document.querySelector('.htmx-request')")
    page.get_by_role("button", name="Edit", exact=True).click()
    card.get_by_role("button", name="Edit item", exact=True).click()
    card.get_by_role("combobox").fill("Oat milk")
    card.get_by_role("button", name="Save", exact=True).click()
    expect(card).to_contain_text("Oat milk")
    card.get_by_role("button", name="Delete item", exact=True).click()
    modal = page.get_by_role("dialog", name="Delete item?", exact=True)
    expect(modal).to_be_visible()
    expect(modal).to_contain_text('"Oat milk" will be permanently deleted.')
    assert len(page.locator('[id^="delete-item-modal"]').all()) == 1


@pytest.mark.parametrize("editing", [False, True])
def test_item_validation_errors_are_swapped_into_the_form(authenticated_page, user, live_server, editing):
    page = authenticated_page
    shopping_list = open_list(page, user, live_server)
    if editing:
        page.get_by_role("button", name="Edit", exact=True).click()
        page.get_by_role("button", name="Edit item", exact=True).click()
        form = page.locator(".shopping-item form[hx-post]")
    else:
        form = page.locator("#item-form form")
    form.evaluate("form => form.noValidate = true")
    form.get_by_role("combobox").fill("")
    form.locator('[name="quantity"]').fill("2 litres")
    form.get_by_role("button", name="Save" if editing else "Add", exact=True).click()
    expect(form).to_contain_text("This field is required.")
    expect(form.locator('[name="quantity"]')).to_have_value("2 litres")
    form.get_by_role("combobox").fill("Oat milk")
    form.get_by_role("button", name="Save" if editing else "Add", exact=True).click()
    expect(page.locator("#items")).to_contain_text("Oat milk")
    if not editing:
        expect(page.locator("#item-form form .errorlist")).to_have_count(0)
    assert shopping_list.items.filter(name="Oat milk").exists()
