import pytest
from playwright.sync_api import expect

from easy_kitchen.models import Article, ShoppingItem, ShoppingList


pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


def open_list(page, user, live_server):
    shopping_list = ShoppingList.objects.create(user=user, title="Groceries")
    ShoppingItem.objects.create(shopping_list=shopping_list, name="Milk", checked=True)
    page.goto(f"{live_server.url}/lists/{shopping_list.pk}/")
    return shopping_list


def test_first_item_replaces_the_empty_message(authenticated_page, user, live_server):
    shopping_list = ShoppingList.objects.create(user=user, title="Groceries")
    page = authenticated_page
    page.goto(f"{live_server.url}/lists/{shopping_list.pk}/")
    expect(page.get_by_text("No items yet.", exact=True)).to_be_visible()

    name = page.get_by_role("combobox", name="Item")
    for article in ["Apple", "Bread"]:
        name.fill(article)
        page.get_by_role("button", name="Add", exact=True).click()
        expect(page.locator(".shopping-item", has_text=article)).to_be_visible()
        expect(page.locator("#empty-message")).to_have_count(0)
    expect(page.locator(".shopping-item")).to_have_count(2)
    page.reload()
    expect(page.locator(".shopping-item")).to_have_count(2)
    expect(page.get_by_text("No items yet.", exact=True)).to_have_count(0)


def test_article_suggestions_require_input(authenticated_page, user, live_server):
    Article.objects.create(user=user, name="Apple")
    page = authenticated_page
    open_list(page, user, live_server)
    name = page.get_by_role("combobox", name="Item")
    suggestions = page.locator(".article-suggestions")

    name.click()
    expect(suggestions).to_be_hidden()
    expect(name).to_have_attribute("aria-expanded", "false")
    for key in ["ArrowDown", "ArrowUp"]:
        name.press(key)
        expect(suggestions).to_be_hidden()
        expect(name).not_to_have_attribute("aria-activedescendant")
    name.fill("   ")
    expect(suggestions).to_be_hidden()

    name.fill("")
    name.press("A")
    expect(page.get_by_role("option", name="Apple", exact=True)).to_be_visible()
    expect(name).to_have_attribute("aria-expanded", "true")
    name.press("ArrowDown")
    name.press("Backspace")
    expect(suggestions).to_be_hidden()
    expect(name).to_have_attribute("aria-expanded", "false")
    expect(name).not_to_have_attribute("aria-activedescendant")
    name.press("ArrowDown")
    expect(suggestions).to_be_hidden()
    expect(name).not_to_have_attribute("aria-activedescendant")


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


def test_item_controls_stay_bound_after_editor_save(authenticated_page, user, live_server):
    page = authenticated_page
    shopping_list = open_list(page, user, live_server)
    page.get_by_role("link", name="Edit list", exact=True).click()
    page.locator("#list-editor-form").get_by_label("Item", exact=True).fill("Oat milk")
    page.get_by_role("button", name="Save", exact=True).first.click()
    expect(page.locator(".shopping-item")).to_contain_text("Oat milk")
    page.route("**/hide-completed/", lambda route: route.fulfill(status=500))
    page.get_by_role("button", name="Hide completed", exact=True).click()
    expect(page.get_by_role("alert").filter(has_text="Your changes could not be saved")).to_be_visible()
    expect(page.locator(".shopping-item")).to_be_visible()
    assert page.locator('[id^="delete-item-modal"]').count() == 0


@pytest.mark.parametrize("editing", [False, True])
def test_item_validation_errors_are_swapped_into_the_form(authenticated_page, user, live_server, editing):
    page = authenticated_page
    shopping_list = open_list(page, user, live_server)
    if editing:
        page.get_by_role("link", name="Edit list", exact=True).click()
        form = page.locator("#list-editor-form")
    else:
        form = page.locator("#item-form form")
    form.evaluate("form => form.noValidate = true")
    form.get_by_label("Item", exact=True).fill("")
    form.get_by_label("Quantity", exact=True).fill("2 litres")
    form.get_by_role("button", name="Save" if editing else "Add", exact=True).click()
    expect(form).to_contain_text("This field is required.")
    expect(form.get_by_label("Quantity", exact=True)).to_have_value("2 litres")
    form.get_by_label("Item", exact=True).fill("Oat milk")
    form.get_by_role("button", name="Save" if editing else "Add", exact=True).click()
    expect(page.locator("#items")).to_contain_text("Oat milk")
    if not editing:
        expect(page.locator("#item-form form .errorlist")).to_have_count(0)
    assert shopping_list.items.filter(name="Oat milk").exists()
