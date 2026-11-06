import pytest
from playwright.sync_api import expect

from easy_kitchen.models import Department, Article, ShoppingList
from easy_kitchen.services import create_item

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


@pytest.mark.parametrize("width", [1280, 390])
def test_article_editor_saves_and_discards_the_whole_draft(authenticated_page, user, live_server, width):
    shopping_list = ShoppingList.objects.create(user=user, title="Market")
    create_item(shopping_list, name="Apple", department="produce", checked=True)
    Article.objects.create(user=user, name="Bread", department=Department.objects.get(code="bread"))
    page = authenticated_page
    page.set_viewport_size({"width": width, "height": 844})
    url = f"{live_server.url}/articles/?list={shopping_list.pk}"
    page.goto(url)
    rows = page.locator(".editor-line:not([hidden])")
    rows.first.get_by_label("Article", exact=True).fill("Pear")
    rows.last.get_by_role("button", name="Remove article", exact=True).click()
    page.get_by_role("button", name="Add article", exact=True).click()
    rows.last.get_by_label("Article", exact=True).fill("Milk")
    assert list(user.articles.values_list("name", flat=True)) == ["Apple", "Bread"]
    page.locator(".article-editor-footer").get_by_role("link", name="Cancel", exact=True).click()
    expect(page.get_by_role("heading", name="Market", exact=True)).to_be_visible()
    page.get_by_role("button", name="Hide completed", exact=True).click()
    expect(page.locator(".shopping-item")).to_be_hidden()
    page.get_by_role("button", name="Show completed", exact=True).click()
    expect(page.locator(".shopping-item")).to_be_visible()
    assert list(user.articles.values_list("name", flat=True)) == ["Apple", "Bread"]
    page.goto(url)
    rows.first.get_by_label("Article", exact=True).fill("Pear")
    rows.first.get_by_label("Department", exact=True).select_option("fresh")
    rows.last.get_by_role("button", name="Remove article", exact=True).click()
    page.get_by_role("button", name="Add article", exact=True).click()
    rows.last.get_by_label("Article", exact=True).fill("Milk")
    rows.last.get_by_label("Department", exact=True).select_option("dairy")
    page.evaluate("window.articleEditorSentinel = true")
    footer = page.locator(".article-editor-footer")
    expect(footer).to_have_css("position", "sticky")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    footer.get_by_role("button", name="Save", exact=True).click()
    expect(rows.first.get_by_label("Article", exact=True)).to_have_value("Milk")
    assert page.evaluate("window.articleEditorSentinel") is True
    assert list(user.articles.values_list("name", "department__code")) == [("Milk", "dairy"), ("Pear", "fresh")]
    item = shopping_list.items.get()
    assert item.name == "Apple" and item.department_code == "produce"
    page.reload()
    expect(rows.last.get_by_label("Article", exact=True)).to_have_value("Pear")
    expect(rows.last.get_by_label("Department", exact=True)).to_have_value("fresh")


def test_validation_retains_the_article_draft_for_retry(authenticated_page, user, live_server):
    Article.objects.create(user=user, name="Apple", department=Department.objects.get(code="produce"))
    Article.objects.create(user=user, name="Bread", department=Department.objects.get(code="bread"))
    page = authenticated_page
    page.goto(f"{live_server.url}/articles/")
    rows = page.locator(".editor-line:not([hidden])")
    rows.first.get_by_label("Article", exact=True).fill("Bread")
    rows.first.get_by_label("Department", exact=True).select_option("fresh")
    page.locator(".article-editor-footer").get_by_role("button", name="Save", exact=True).click()
    expect(rows.first).to_contain_text("An article with this name already exists.")
    expect(rows.first.get_by_label("Department", exact=True)).to_have_value("fresh")
    assert user.articles.get(name="Apple").department_code == "produce"
    rows.first.get_by_label("Article", exact=True).fill("Pear")
    page.locator(".article-editor-footer").get_by_role("button", name="Save", exact=True).click()
    expect(rows.last.get_by_label("Article", exact=True)).to_have_value("Pear")
    assert user.articles.get(name="Pear").department_code == "fresh"
