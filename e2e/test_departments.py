import pytest
from playwright.sync_api import expect

from easy_kitchen.models import Department, Article, ShoppingList
from easy_kitchen.services import create_item

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


@pytest.mark.parametrize("selection", ["typing", "mouse", "keyboard"])
def test_department_defaults_and_grouping(authenticated_page, user, live_server, selection):
    Article.objects.create(user=user, name="Milk", department=Department.objects.get(code="dairy"))
    shopping_list = ShoppingList.objects.create(user=user, title="Groceries")
    create_item(shopping_list, name="Mystery", department="")
    page = authenticated_page
    page.goto(f"{live_server.url}/lists/{shopping_list.pk}/")
    name = page.get_by_role("combobox", name="Item", exact=True)
    department = page.get_by_label("Department", exact=True)
    name.fill("Milk" if selection == "typing" else "Mil")
    if selection == "mouse":
        page.get_by_role("option", name="Milk", exact=True).click()
    elif selection == "keyboard":
        name.press("ArrowDown")
        name.press("Enter")
    expect(department).to_have_value("dairy")
    department.select_option("fresh")
    page.get_by_role("button", name="Add", exact=True).click()
    fresh = page.locator('.department-group[data-department="fresh"]')
    expect(fresh).to_contain_text("Milk")
    expect(page.locator('.department-group[data-department=""]')).to_contain_text("Mystery")
    expect(department).to_have_value("")
    name.fill("Milk")
    expect(department).to_have_value("fresh")
    department.select_option("dairy")
    page.get_by_role("button", name="Add", exact=True).click()
    expect(fresh).to_have_count(0)
    dairy = page.locator('.department-group[data-department="dairy"]')
    expect(dairy.locator(".shopping-item")).to_have_count(1)
    assert Article.objects.get(user=user, name="Milk").department_code == "dairy"
    page.reload()
    expect(dairy).to_contain_text("Milk")
    page.get_by_role("button", name="Hide completed", exact=True).click()
    dairy.get_by_role("button", name="Milk", exact=True).click()
    expect(dairy).to_be_hidden()
    page.get_by_role("button", name="Show completed", exact=True).click()
    expect(dairy).to_be_visible()


def test_editor_prefills_and_saves_departments(authenticated_page, user, live_server):
    Article.objects.create(user=user, name="Apple", department=Department.objects.get(code="produce"))
    shopping_list = ShoppingList.objects.create(user=user, title="Groceries")
    create_item(shopping_list, name="Milk", department="dairy")
    page = authenticated_page
    page.goto(f"{live_server.url}/lists/{shopping_list.pk}/")
    page.get_by_role("link", name="Edit list", exact=True).click()
    line = page.locator(".editor-line").first
    expect(line.get_by_label("Department", exact=True)).to_have_value("dairy")
    line.get_by_label("Item", exact=True).fill("Apple")
    expect(line.get_by_label("Department", exact=True)).to_have_value("produce")
    line.get_by_label("Department", exact=True).select_option("fresh")
    page.get_by_role("button", name="Save", exact=True).first.click()
    expect(page.locator('.department-group[data-department="fresh"]')).to_contain_text("Apple")
    assert Article.objects.get(user=user, name="Apple").department_code == "fresh"
    page.reload()
    expect(page.locator('.department-group[data-department="fresh"]')).to_contain_text("Apple")
