import re

import pytest
from playwright.sync_api import expect


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_saved_articles_are_suggested_and_can_be_renamed(authenticated_page):
    page = authenticated_page
    articles = page.get_by_role("link", name="Articles")
    logout = page.get_by_role("button", name="Log out")
    expect(articles).to_be_visible()
    assert articles.bounding_box()["x"] < logout.bounding_box()["x"]

    page.get_by_role("link", name="New list").click()
    page.locator("input[name=title]").fill("Vorrat")
    page.locator("input[name=date]").fill("2026-11-01")
    page.get_by_role("button", name="Save").click()
    page.get_by_role("combobox", name="Item").fill("Naturtofu")
    page.get_by_role("button", name="Add").click()
    expect(page.locator(".shopping-item", has_text="Naturtofu")).to_be_visible()

    page.get_by_role("link", name="Articles").click()
    expect(page.get_by_role("heading", name="Articles")).to_be_visible()
    name = page.get_by_role("textbox", name="Edit Naturtofu")
    expect(name).to_have_value("Naturtofu")
    name.fill("Räuchertofu")
    name.locator("xpath=ancestor::form[1]").get_by_role("button", name="Save").click()
    expect(page.get_by_role("textbox", name="Edit Räuchertofu")).to_have_value("Räuchertofu")

    page.get_by_role("link", name="EasyList").click()
    page.get_by_role("link", name="Vorrat").click()
    expect(page.locator('#articles option[value="Räuchertofu"]')).to_have_count(1)
    expect(page.locator('#articles option[value="Naturtofu"]')).to_have_count(0)


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_article_suggestions_open_at_the_start_of_the_input(authenticated_page):
    page = authenticated_page
    page.get_by_role("link", name="New list").click()
    page.locator("input[name=title]").fill("Vorrat")
    page.locator("input[name=date]").fill("2026-11-01")
    page.get_by_role("button", name="Save").click()
    name = page.get_by_role("combobox", name="Item")
    name.fill("Avocado")
    page.get_by_role("button", name="Add").click()
    expect(page.locator('#articles option[value="Avocado"]')).to_have_count(1)

    name.click()
    suggestions = page.get_by_role("listbox", name="Articles")
    expect(suggestions.get_by_role("option", name="Avocado")).to_be_visible()
    input_box = name.bounding_box()
    suggestions_box = suggestions.bounding_box()
    assert abs(suggestions_box["x"] - input_box["x"]) <= 1
    assert suggestions_box["y"] >= input_box["y"] + input_box["height"] - 1

    suggestions.get_by_role("option", name="Avocado").click()
    expect(name).to_have_value("Avocado")


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_articles_return_to_the_page_they_were_opened_from(authenticated_page):
    page = authenticated_page
    page.get_by_role("link", name="New list").click()
    page.locator("input[name=title]").fill("Vorrat")
    page.locator("input[name=date]").fill("2026-11-01")
    page.get_by_role("button", name="Save").click()
    page.get_by_role("link", name="Articles").click()
    page.get_by_role("link", name="Vorrat").click()
    expect(page.get_by_role("heading", name="Vorrat")).to_be_visible()

    page.get_by_role("link", name="EasyList").click()
    page.get_by_role("link", name="Articles").click()
    page.locator("main").get_by_role("link", name="Shopping lists").click()
    expect(page.get_by_role("heading", name="Shopping lists")).to_be_visible()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_article_actions_stay_beside_the_name_on_a_phone(authenticated_page):
    page = authenticated_page
    page.set_viewport_size({"width": 390, "height": 844})
    page.get_by_role("link", name="Articles").click()
    page.get_by_label("Article").fill("Apfel")
    page.get_by_role("button", name="Add").click()

    row = page.locator(".article-row")
    name = row.get_by_role("textbox", name="Edit Apfel")
    save = row.get_by_role("button", name="Save")
    delete = row.get_by_role("button", name="Delete")
    expect(name).to_be_visible()
    name_box = name.bounding_box()
    save_box = save.bounding_box()
    delete_box = delete.bounding_box()
    assert abs(name_box["y"] - save_box["y"]) < 8
    assert abs(name_box["y"] - delete_box["y"]) < 8
    assert name_box["x"] + name_box["width"] <= save_box["x"]
    assert save_box["x"] + save_box["width"] <= delete_box["x"]
    assert delete_box["x"] + delete_box["width"] <= 390


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_user_can_create_and_check_an_item(authenticated_page):
    page = authenticated_page

    page.get_by_role("link", name="New list").click()
    page.locator("input[name=title]").fill("Asiatische Erdnuss-Tofu-Pfanne")
    page.locator("input[name=date]").fill("2026-10-30")
    page.get_by_role("button", name="Save").click()

    page.get_by_role("combobox", name="Item").fill("Naturtofu")
    page.get_by_label("Quantity").fill("400 g")
    page.get_by_role("button", name="Add").click()

    item = page.locator(".shopping-item", has_text="Naturtofu")
    item.wait_for()
    item.get_by_role("button", name="Naturtofu").click()
    expect(item).to_have_class(re.compile(r".*\bchecked\b.*"))
    expect(item.locator(".item-quantity")).to_have_css("text-decoration-line", "line-through")


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_adding_the_same_item_again_shows_both_quantities(authenticated_page):
    page = authenticated_page
    page.get_by_role("link", name="New list").click()
    page.locator("input[name=title]").fill("Getränke")
    page.locator("input[name=date]").fill("2026-11-01")
    page.get_by_role("button", name="Save").click()

    page.get_by_role("combobox", name="Item").fill("Milch")
    page.get_by_role("textbox", name="Quantity").fill("1 l")
    page.get_by_role("button", name="Add").click()
    expect(page.locator(".shopping-item", has_text="Milch")).to_contain_text("1 l")

    page.get_by_role("combobox", name="Item").fill("Milch")
    page.get_by_role("textbox", name="Quantity").fill("500 ml")
    page.get_by_role("button", name="Add").click()

    items = page.locator(".shopping-item", has_text="Milch")
    expect(items).to_have_count(1)
    expect(items).to_contain_text("1 l")
    expect(items).to_contain_text("500 ml")

    page.get_by_role("combobox", name="Item").fill("Milch")
    page.get_by_role("textbox", name="Quantity").fill("1 l")
    page.get_by_role("button", name="Add").click()
    expect(items).to_contain_text("2 l, 500 ml")


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_user_cannot_see_another_users_list(authenticated_page, other_user):
    from shopping.models import ShoppingList

    ShoppingList.objects.create(user=other_user, title="Private Liste")
    page = authenticated_page
    expect(page.get_by_text("Private Liste")).to_have_count(0)


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_user_can_hide_and_reset_completed_items(authenticated_page, user):
    from shopping.models import ShoppingItem, ShoppingList

    shopping_list = ShoppingList.objects.create(user=user, title="Wocheneinkauf")
    completed = ShoppingItem.objects.create(shopping_list=shopping_list, name="Tofu", checked=True)
    ShoppingItem.objects.create(shopping_list=shopping_list, name="Reis")
    page = authenticated_page
    page.route("**/easylist.css", lambda route: route.abort())
    page.goto(f"{page.url.rstrip('/')}/lists/{shopping_list.pk}/")

    completed_item = page.locator(f'.shopping-item[data-item-id="{completed.pk}"]')
    page.get_by_role("button", name="Hide completed").click()
    expect(completed_item).to_be_hidden()

    page.get_by_role("button", name="Mark all as not completed").click()
    expect(completed_item).to_be_visible()
    expect(completed_item).not_to_have_class(re.compile(r".*\bchecked\b.*"))


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_user_can_edit_a_list_from_the_overview(authenticated_page, user):
    from shopping.models import ShoppingList

    shopping_list = ShoppingList.objects.create(user=user, title="Alter Titel")
    page = authenticated_page
    page.reload()
    card = page.locator(".list-card", has_text="Alter Titel")

    card.get_by_role("link", name="Edit").click()
    page.locator("input[name=title]").fill("Neuer Titel")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_role("heading", name="Shopping lists")).to_be_visible()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_user_can_edit_a_list_from_its_detail_page(authenticated_page, user):
    from shopping.models import ShoppingList

    shopping_list = ShoppingList.objects.create(user=user, title="Alter Titel")
    page = authenticated_page
    page.goto(f"{page.url.rstrip('/')}/lists/{shopping_list.pk}/")

    page.get_by_role("link", name="Edit list").click()
    page.locator("input[name=title]").fill("Neuer Titel")
    page.get_by_role("button", name="Save").click()

    expect(page.get_by_role("heading", name="Neuer Titel")).to_be_visible()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_user_can_delete_a_list_from_the_overview_modal(authenticated_page, user):
    from shopping.models import ShoppingList

    ShoppingList.objects.create(user=user, title="Zu löschen")
    page = authenticated_page
    page.reload()

    card = page.locator(".list-card", has_text="Zu löschen")
    card.get_by_role("button", name="Delete list").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    dialog.get_by_role("button", name="Delete permanently").click()
    expect(page.get_by_text("Zu löschen")).to_have_count(0)


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_user_can_reorder_items_with_drag_and_drop(authenticated_page, user):
    from shopping.models import ShoppingItem, ShoppingList

    shopping_list = ShoppingList.objects.create(user=user, title="Wocheneinkauf")
    tofu = ShoppingItem.objects.create(shopping_list=shopping_list, name="Tofu", position=1)
    rice = ShoppingItem.objects.create(shopping_list=shopping_list, name="Reis", position=2)
    page = authenticated_page
    page.goto(f"{page.url.rstrip('/')}/lists/{shopping_list.pk}/")

    tofu_handle = page.locator(f'.shopping-item[data-item-id="{tofu.pk}"]').get_by_role("button", name="Move")
    rice_handle = page.locator(f'.shopping-item[data-item-id="{rice.pk}"]').get_by_role("button", name="Move")
    with page.expect_response(lambda response: "/reorder/" in response.url and response.request.method == "POST"):
        tofu_handle.drag_to(rice_handle)
    page.reload()

    item_names = page.locator(".shopping-item .item-name").all_text_contents()
    assert item_names == ["Reis", "Tofu"]


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_interface_uses_the_test_settings_language(authenticated_page):
    page = authenticated_page
    page.set_extra_http_headers({"Accept-Language": "de"})
    page.reload()
    expect(page.get_by_role("heading", name="Shopping lists")).to_be_visible()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_user_can_import_a_json_shopping_list(authenticated_page):
    page = authenticated_page

    page.get_by_role("link", name="Import JSON").click()
    page.get_by_label("Shopping-list JSON").fill(
        '''{
          "lists": [{
            "title": "Tofu pan",
            "date": "2026-10-31",
            "items": [{"name": "Tofu", "quantity": "400 g"}]
          }]
        }'''
    )
    page.get_by_role("button", name="Import").click()

    expect(page.get_by_role("link", name="Tofu pan")).to_be_visible()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_recipe_ingredients_can_be_added_to_a_new_list(authenticated_page):
    page = authenticated_page
    page.get_by_role("link", name="Recipes").click()
    page.get_by_role("link", name="New recipe").click()
    page.get_by_label("Title").fill("Pancakes")
    page.get_by_label("Description").fill("Sunday breakfast")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_role("heading", name="Pancakes")).to_be_visible()

    page.get_by_label("Ingredient").fill("Flour")
    page.get_by_label("quantity").fill("200 g")
    page.locator("#ingredient-form").get_by_role("button", name="Add").click()
    expect(page.locator("#ingredients")).to_contain_text("Flour")
    page.get_by_label("Step").fill("Mix the batter")
    page.locator("#step-form").get_by_role("button", name="Add").click()
    expect(page.locator("#steps")).to_contain_text("Mix the batter")

    page.get_by_label("New list").fill("Weekend")
    page.get_by_role("button", name="Add to list").click()
    expect(page.get_by_role("heading", name="Weekend")).to_be_visible()
    item = page.locator(".shopping-item", has_text="Flour")
    expect(item).to_be_visible()
    expect(item.locator(".item-quantity")).to_have_text("200 g")


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_logged_in_user_sees_swagger_ui(page, live_server, user):
    from django.contrib.staticfiles.views import serve
    from django.urls import clear_url_caches, re_path
    from project import urls

    def serve_static(request, path):
        return serve(request, path, insecure=True)

    static_pattern = re_path(r"^static/(?P<path>.*)$", serve_static)
    urls.urlpatterns.append(static_pattern)
    clear_url_caches()
    try:
        page.goto(f"{live_server.url}/accounts/login/")
        page.get_by_label("Username").fill(user.username)
        page.get_by_label("Password").fill("test-password")
        page.get_by_role("button", name="Sign in").click()
        page.get_by_role("heading", name="Shopping lists").wait_for()

        page.goto(f"{live_server.url}/api/v1/")

        swagger = page.locator("#swagger-ui")
        expect(swagger.get_by_text("EasyList API")).to_be_visible()
        for path in (
            "/api/v1/shopping-lists/",
            "/api/v1/shopping-lists/{id}/",
            "/api/v1/shopping-lists/{id}/reorder/",
            "/api/v1/shopping-lists/import_json/",
        ):
            expect(swagger.get_by_text(path, exact=True).first).to_be_visible()
    finally:
        urls.urlpatterns.remove(static_pattern)
        clear_url_caches()
