import pytest
from playwright.sync_api import expect

from easy_kitchen.models import ShoppingList
from easy_kitchen.services import create_item

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


@pytest.mark.parametrize("width", [1280, 390])
def test_departments_are_edited_as_one_private_draft(authenticated_page, user, other_user, live_server, width):
    shopping_list = ShoppingList.objects.create(user=user, title="Market")
    create_item(shopping_list, name="Milk", department="dairy")
    create_item(shopping_list, name="Bread", department="bread")
    other_user.departments.create(code="private", name="Other user's private department")
    page = authenticated_page
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(f"{live_server.url}/lists/{shopping_list.pk}/")
    page.get_by_role("button", name=user.username, exact=True).click()
    page.get_by_role("link", name="Edit departments", exact=True).click()
    expect(page.get_by_role("heading", name="Departments", exact=True)).to_be_visible()
    assert "Other user's private department" not in page.locator("input").evaluate_all("inputs => inputs.map(input => input.value)")
    rows = page.locator(".editor-line:not([hidden])")
    dairy = rows.filter(has=page.locator('input[value="Dairy products"]'))
    dairy.get_by_label("Department", exact=True).fill("Discarded dairy")
    page.locator(".department-editor-footer").get_by_role("link", name="Cancel", exact=True).click()
    expect(page.get_by_role("heading", name="Market", exact=True)).to_be_visible()
    assert user.departments.get(code="dairy").name == "Dairy products"
    page.get_by_role("button", name=user.username, exact=True).click()
    page.get_by_role("link", name="Edit departments", exact=True).click()
    dairy.get_by_label("Department", exact=True).fill("My dairy")
    rows.filter(has=page.locator('input[value="Bread"]')).get_by_role("button", name="Remove department", exact=True).click()
    page.get_by_role("button", name="Add department", exact=True).click()
    rows.last.get_by_label("Department", exact=True).fill("Garden supplies")
    assert user.departments.get(code="dairy").name == "Dairy products"
    footer = page.locator(".department-editor-footer")
    expect(footer).to_have_css("position", "sticky")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.evaluate("window.departmentEditorSentinel = true")
    footer.get_by_role("button", name="Save", exact=True).click()
    expect(page.locator('input[value="My dairy"]')).to_be_visible()
    assert page.evaluate("window.departmentEditorSentinel") is True
    assert user.departments.get(code="dairy").name == "My dairy"
    assert other_user.departments.get(code="dairy").name == "Dairy products"
    assert user.departments.filter(name="Garden supplies").exists()
    assert not user.departments.filter(code="bread").exists()
    assert shopping_list.items.get(name="Bread").department_id is None
    page.locator(".department-editor-footer").get_by_role("link", name="Cancel", exact=True).click()
    expect(page.get_by_role("heading", name="Market", exact=True)).to_be_visible()
    options = page.get_by_label("Department", exact=True)
    expect(options.locator('option[value="dairy"]')).to_have_text("My dairy")
    expect(options.locator('option[value="bread"]')).to_have_count(0)
    expect(options.locator('option[value="garden-supplies"]')).to_have_text("Garden supplies")
    expect(page.locator('.department-group[data-department="dairy"]')).to_contain_text("Milk")
    expect(page.locator('.department-group[data-department=""]')).to_contain_text("Bread")


def test_duplicate_department_errors_preserve_the_draft(authenticated_page, user, live_server):
    page = authenticated_page
    page.goto(f"{live_server.url}/departments/")
    page.get_by_role("button", name="Add department", exact=True).click()
    row = page.locator(".editor-line:not([hidden])").last
    row.get_by_label("Department", exact=True).fill(" bread ")
    page.locator(".department-editor-footer").get_by_role("button", name="Save", exact=True).click()
    expect(row).to_contain_text("A department with this name already exists.")
    expect(row.get_by_label("Department", exact=True)).to_have_value(" bread ")
    assert user.departments.count() == 21
    row.get_by_label("Department", exact=True).fill("Garden")
    page.locator(".department-editor-footer").get_by_role("button", name="Save", exact=True).click()
    expect(page.locator('input[value="Garden"]')).to_be_visible()
    assert user.departments.count() == 22
