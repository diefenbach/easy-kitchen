import pytest
from playwright.sync_api import expect

from easy_kitchen.models import Article, Recipe, ShoppingItem, ShoppingList
from easy_kitchen.services import create_recipe


pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


@pytest.mark.parametrize("kind", ["recipe", "list"])
@pytest.mark.parametrize("direct", [False, True])
def test_editors_work_without_sortable(authenticated_page, user, live_server, kind, direct):
    page = authenticated_page
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/Sortable.min.js", lambda route: route.abort())
    if kind == "recipe":
        collection = create_recipe(user, title="Soup", ingredients=[{"name": "First"}, {"name": "Second"}], steps=["Chop"])
        detail = f"{live_server.url}/recipes/{collection.pk}/"
        prefix, label, remove, add = "ingredients", "Ingredient", "Remove ingredient", "Add ingredient"
    else:
        collection = ShoppingList.objects.create(user=user, title="Market")
        for name in ("First", "Second"):
            ShoppingItem.objects.create(shopping_list=collection, name=name)
        detail = f"{live_server.url}/lists/{collection.pk}/"
        prefix, label, remove, add = "items", "Item", "Remove item", "Add item"
    page.goto(detail + "edit/" if direct else detail)
    if not direct:
        page.get_by_role("link", name="Edit recipe" if kind == "recipe" else "Edit list", exact=True).click()
    rows = page.locator(f'[data-editor-lines="{prefix}"] .editor-line:not([hidden])')
    expect(rows.first.locator("[data-editor-up]")).to_be_disabled()
    expect(rows.first.locator(".editor-drag")).to_be_hidden()
    rows.first.get_by_role("button", name=remove, exact=True).click()
    page.get_by_role("button", name=add, exact=True).click()
    rows.last.get_by_label(label, exact=True).fill("Third")
    rows.last.get_by_role("button", name="Move up", exact=True).click()
    if kind == "recipe":
        page.get_by_role("button", name="Add step", exact=True).click()
        page.get_by_label("Step", exact=True).last.fill("Serve")
    page.get_by_role("button", name="Save", exact=True).first.click()
    expect(page).to_have_url(detail)
    manager = collection.ingredients if kind == "recipe" else collection.items
    assert list(manager.values_list("name", flat=True)) == ["Third", "Second"]
    if kind == "recipe":
        assert list(collection.steps.values_list("text", flat=True)) == ["Chop", "Serve"]
    assert errors == []


@pytest.mark.parametrize("kind", ["lists", "recipes", "recipe-editor", "list-editor"])
def test_sortables_are_destroyed_once_when_htmx_replaces_their_elements(authenticated_page, user, live_server, kind):
    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Onion"}], steps=["Chop"])
    shopping_list = ShoppingList.objects.create(user=user, title="Market")
    ShoppingItem.objects.create(shopping_list=shopping_list, name="Onion")
    page = authenticated_page
    if kind == "recipe-editor":
        path, count = f"/recipes/{recipe.pk}/edit/", 2
    elif kind == "list-editor":
        path, count = f"/lists/{shopping_list.pk}/edit/", 1
    else:
        path, count = f"/{kind}/", 1
    page.goto(live_server.url + path)
    page.evaluate("""() => {
      window.destroyedSortables = 0;
      const destroy = Sortable.prototype.destroy;
      Sortable.prototype.destroy = function () {
        window.destroyedSortables += 1;
        return destroy.call(this);
      };
    }""")
    page.evaluate("""() => htmx.ajax('GET', '/lists/', {
      target: 'main', select: 'main', swap: 'outerHTML'
    })""")
    assert page.evaluate("window.destroyedSortables") == count


def test_article_suggestions_limit_results_and_search_the_full_catalog(authenticated_page, user, live_server):
    Article.objects.bulk_create([Article(user=user, name=f"Article {index:03d}") for index in range(60)])
    shopping_list = ShoppingList.objects.create(user=user, title="Market")
    page = authenticated_page
    page.goto(f"{live_server.url}/lists/{shopping_list.pk}/")
    search = page.get_by_role("combobox", name="Item", exact=True)
    search.focus()
    expect(page.get_by_role("option")).to_have_count(20)
    search.fill("Article 059")
    expect(page.get_by_role("option")).to_have_count(1)
    search.press("ArrowUp")
    search.press("Enter")
    expect(search).to_have_value("Article 059")
    page.get_by_role("button", name="Add", exact=True).click()
    expect(page.locator(".shopping-item")).to_contain_text("Article 059")


def test_recipe_suggestions_limit_results_and_search_the_full_catalog(authenticated_page, user, live_server):
    Recipe.objects.bulk_create([Recipe(user=user, title=f"Recipe {index:03d}") for index in range(60)])
    page = authenticated_page
    page.goto(f"{live_server.url}/planner/")
    day = page.locator(".planner-day").first
    search = day.locator(".recipe-search")
    search.focus()
    expect(day.get_by_role("option")).to_have_count(20)
    search.fill("Recipe 059")
    expect(day.get_by_role("option")).to_have_count(1)
    search.press("ArrowDown")
    search.press("Enter")
    day.get_by_role("button", name="Save plan", exact=True).click()
    expect(day.get_by_role("link", name="Recipe 059", exact=True)).to_be_visible()
