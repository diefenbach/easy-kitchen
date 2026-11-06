from datetime import date

import pytest
from playwright.sync_api import expect

from easy_kitchen.services import create_item, create_shopping_list


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_quantity_overflow_shows_form_error_and_preserves_item(authenticated_page, user, live_server):
    shopping_list = create_shopping_list(user, title="Quantity limit", date=date.today())
    item = create_item(shopping_list, name="Milk", quantity="1 " + "a" * 98)
    page = authenticated_page
    page.goto(f"{live_server.url}/lists/{shopping_list.pk}/")
    page.get_by_role("combobox", name="Item", exact=True).fill("Milk")
    page.locator('#item-form input[name="quantity"]').fill("1 " + "b" * 98)
    page.get_by_role("button", name="Add", exact=True).click()
    expect(page.locator("#item-form")).to_contain_text("The combined quantity exceeds 100 characters.")
    expect(page.locator(".shopping-item")).to_have_count(1)
    item.refresh_from_db()
    assert item.quantity == "1 " + "a" * 98


