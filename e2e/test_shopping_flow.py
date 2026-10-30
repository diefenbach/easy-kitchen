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
