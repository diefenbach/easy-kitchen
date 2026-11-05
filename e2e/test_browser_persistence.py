import pytest
from playwright.sync_api import expect

from easy_kitchen.models import ShoppingItem, ShoppingList
from easy_kitchen.services import create_recipe


pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


def open_list(page, user, live_server):
    shopping_list = ShoppingList.objects.create(user=user, title="Groceries")
    ShoppingItem.objects.create(shopping_list=shopping_list, name="Milk", checked=True)
    page.goto(f"{live_server.url}/lists/{shopping_list.pk}/")
    return shopping_list


@pytest.mark.parametrize("failure", [403, 500, "offline"])
def test_hide_completed_failure_restores_confirmed_state(authenticated_page, user, live_server, failure):
    page = authenticated_page
    shopping_list = open_list(page, user, live_server)
    errors = []
    page.on("pageerror", lambda error: errors.append(error))

    def fail(route):
        if failure == "offline":
            route.abort()
        else:
            route.fulfill(status=failure, body="Could not save")

    page.route("**/hide-completed/", fail)
    page.get_by_role("button", name="Hide completed", exact=True).click()
    expect(page.get_by_role("alert")).to_contain_text("Your changes could not be saved")
    expect(page.get_by_role("button", name="Hide completed", exact=True)).to_be_enabled()
    expect(page.locator(".shopping-item")).to_be_visible()
    shopping_list.refresh_from_db()
    assert not shopping_list.hide_completed_items
    assert errors == []


def test_hide_completed_blocks_overlapping_requests(authenticated_page, user, live_server):
    page = authenticated_page
    shopping_list = open_list(page, user, live_server)
    requests = []
    page.route("**/hide-completed/", lambda route: requests.append(route))
    toggle = page.locator("#toggle-checked-items")
    toggle.click()
    expect(toggle).to_be_disabled()
    toggle.dispatch_event("click")
    assert len(requests) == 1
    requests[0].continue_()
    expect(toggle).to_be_enabled()
    toggle.click()
    expect(toggle).to_be_disabled()
    page.wait_for_function("document.querySelector('#toggle-checked-items').disabled")
    assert len(requests) == 2
    requests[1].continue_()
    expect(toggle).to_be_enabled()
    page.reload()
    expect(page.locator(".shopping-item")).to_be_visible()
    shopping_list.refresh_from_db()
    assert not shopping_list.hide_completed_items


@pytest.mark.parametrize("kind", ["items", "lists", "recipes"])
def test_failed_reorder_rolls_back_and_blocks_another_drag(authenticated_page, user, live_server, kind):
    page = authenticated_page
    if kind == "items":
        shopping_list = ShoppingList.objects.create(user=user, title="Groceries")
        for name in ("First", "Second"):
            ShoppingItem.objects.create(shopping_list=shopping_list, name=name)
        page.goto(f"{live_server.url}/lists/{shopping_list.pk}/")
        cards = page.locator("#items .shopping-item")
        manager = shopping_list.items
        ids = "data-item-id"
    else:
        for name in ("First", "Second"):
            if kind == "lists":
                ShoppingList.objects.create(user=user, title=name)
            else:
                create_recipe(user, title=name)
        page.goto(f"{live_server.url}/{kind}/")
        cards = page.locator("[data-card-reorder] > [data-list-id]")
        manager = getattr(user, "shopping_lists" if kind == "lists" else "recipes")
        ids = "data-list-id"
    def order():
        return list(manager.values_list("pk", flat=True))

    before = order()
    page.get_by_role("button", name="Edit", exact=True).click()
    pending = []
    page.route("**/reorder/", lambda route: pending.append(route))
    cards.nth(0).get_by_role("button", name="Move", exact=True).drag_to(cards.nth(1).get_by_role("button", name="Move", exact=True))
    expect(cards.first.locator("..")).to_have_attribute("aria-busy", "true")
    assert len(pending) == 1
    cards.nth(0).get_by_role("button", name="Move", exact=True).drag_to(cards.nth(1).get_by_role("button", name="Move", exact=True))
    assert len(pending) == 1
    pending[0].fulfill(status=500, body="Could not save")
    expect(page.get_by_role("alert")).to_contain_text("Your changes could not be saved")
    assert [int(value) for value in cards.evaluate_all(f"nodes => nodes.map(node => node.getAttribute('{ids}'))")] == before
    assert order() == before
    page.unroute("**/reorder/")
    cards.nth(0).get_by_role("button", name="Move", exact=True).drag_to(cards.nth(1).get_by_role("button", name="Move", exact=True))
    expect(cards.first.locator("..")).not_to_have_attribute("aria-busy", "true")
    page.reload()
    assert order() == before[::-1]
