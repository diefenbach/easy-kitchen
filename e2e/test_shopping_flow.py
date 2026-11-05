import re

import pytest
from playwright.sync_api import expect


def show_edit_actions(page):
    page.get_by_role("button", name="Edit", exact=True).click()


def open_shopping_lists(page):
    page.get_by_role("link", name="Shopping lists", exact=True).click()
    expect(page).to_have_url(re.compile(r"/lists/$"))


def open_account_menu(page):
    page.get_by_role("button", name="e2e-user", exact=True).click()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_saved_articles_are_suggested_and_can_be_renamed(authenticated_page):
    page = authenticated_page
    overview = page.get_by_role("link", name="Overview", exact=True)
    lists = page.get_by_role("link", name="Shopping lists", exact=True)
    account = page.get_by_role("button", name="e2e-user", exact=True)
    expect(overview).to_be_visible()
    recipes = page.get_by_role("link", name="Recipes", exact=True)
    assert overview.bounding_box()["x"] < recipes.bounding_box()["x"] < lists.bounding_box()["x"] < account.bounding_box()["x"]

    page.get_by_role("link", name="New list").click()
    page.locator("input[name=title]").fill("Vorrat")
    page.locator("input[name=date]").fill("2026-11-01")
    page.get_by_role("button", name="Save").click()
    page.get_by_role("combobox", name="Item").fill("Naturtofu")
    page.get_by_role("button", name="Add").click()
    expect(page.locator(".shopping-item", has_text="Naturtofu")).to_be_visible()

    open_account_menu(page)
    page.get_by_role("link", name="Edit articles", exact=True).click()
    expect(page.get_by_role("heading", name="Articles")).to_be_visible()
    name = page.get_by_role("textbox", name="Edit Naturtofu")
    expect(name).to_have_value("Naturtofu")
    name.fill("Räuchertofu")
    name.locator("xpath=ancestor::form[1]").get_by_role("button", name="Save").click()
    expect(page.get_by_role("textbox", name="Edit Räuchertofu")).to_have_value("Räuchertofu")

    page.get_by_role("link", name="Easy Kitchen").click()
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
    expect(name).to_be_focused()

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
    open_account_menu(page)
    page.get_by_role("link", name="Edit articles", exact=True).click()
    page.get_by_role("link", name="Vorrat").click()
    expect(page.get_by_role("heading", name="Vorrat")).to_be_visible()

    page.get_by_role("link", name="Easy Kitchen").click()
    open_account_menu(page)
    page.get_by_role("link", name="Edit articles", exact=True).click()
    page.locator("main").get_by_role("link", name="Shopping lists").click()
    expect(page.get_by_role("heading", name="Shopping lists")).to_be_visible()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_article_actions_stay_beside_the_name_on_a_phone(authenticated_page):
    page = authenticated_page
    page.set_viewport_size({"width": 390, "height": 844})
    open_account_menu(page)
    page.get_by_role("link", name="Edit articles", exact=True).click()
    page.get_by_label("Article", exact=True).fill("Apfel")
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
    from easy_kitchen.models import ShoppingList

    ShoppingList.objects.create(user=other_user, title="Private Liste")
    page = authenticated_page
    expect(page.get_by_text("Private Liste")).to_have_count(0)


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_user_can_hide_and_reset_completed_items(authenticated_page, user):
    from easy_kitchen.models import ShoppingItem, ShoppingList

    shopping_list = ShoppingList.objects.create(user=user, title="Wocheneinkauf")
    completed = ShoppingItem.objects.create(shopping_list=shopping_list, name="Tofu", checked=True)
    ShoppingItem.objects.create(shopping_list=shopping_list, name="Reis")
    page = authenticated_page
    page.route("**/easykitchen.css", lambda route: route.abort())
    page.goto(f"{page.url.rstrip('/')}/lists/{shopping_list.pk}/")

    completed_item = page.locator(f'.shopping-item[data-item-id="{completed.pk}"]')
    page.get_by_role("button", name="Hide completed").click()
    expect(completed_item).to_be_hidden()

    page.get_by_role("button", name="Delete completed").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    page.locator("#delete-completed-modal").get_by_role("button", name="Delete permanently").click()
    expect(completed_item).to_have_count(0)
    expect(page.locator(".shopping-item", has_text="Reis")).to_be_visible()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_hide_completed_persists_after_reload(authenticated_page, user):
    from easy_kitchen.models import ShoppingItem, ShoppingList

    shopping_list = ShoppingList.objects.create(user=user, title="Wocheneinkauf")
    completed = ShoppingItem.objects.create(shopping_list=shopping_list, name="Tofu", checked=True)
    ShoppingItem.objects.create(shopping_list=shopping_list, name="Reis")
    page = authenticated_page
    page.goto(f"{page.url.rstrip('/')}/lists/{shopping_list.pk}/")

    completed_item = page.locator(f'.shopping-item[data-item-id="{completed.pk}"]')
    with page.expect_response(f"**/lists/{shopping_list.pk}/hide-completed/") as saved:
        page.get_by_role("button", name="Hide completed").click()
    assert saved.value.status == 204
    expect(completed_item).to_be_hidden()

    page.reload()
    expect(completed_item).to_be_hidden()
    expect(page.get_by_role("button", name="Show completed")).to_be_visible()

    with page.expect_response(f"**/lists/{shopping_list.pk}/hide-completed/") as saved:
        page.get_by_role("button", name="Show completed").click()
    assert saved.value.status == 204
    expect(completed_item).to_be_visible()

    page.reload()
    expect(completed_item).to_be_visible()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_edit_mode_starts_off_and_resets_when_the_page_reloads(authenticated_page, user):
    from easy_kitchen.models import ShoppingItem, ShoppingList
    from easy_kitchen.services import create_recipe

    shopping_list = ShoppingList.objects.create(user=user, title="Wocheneinkauf")
    ShoppingItem.objects.create(shopping_list=shopping_list, name="Tofu", position=1)
    recipe_title = "Asiatische Erdnuss-Ingwer-Pfanne mit knusprigem Tofu"
    create_recipe(
        user,
        title=recipe_title,
        description="Eine würzige, vegane Gemüsepfanne mit knusprigem Tofu, Edamame und cremiger Sauce.",
        ingredients=[{"name": "Flour", "quantity": "200 g"}],
    )
    page = authenticated_page
    page.reload()
    open_shopping_lists(page)

    card = page.locator(".list-card", has_text="Wocheneinkauf")
    overview_edit = card.get_by_role("link", name="Edit", exact=True, include_hidden=True)
    expect(overview_edit).to_be_hidden()
    show_edit_actions(page)
    expect(overview_edit).to_be_visible()
    page.get_by_role("button", name="Done", exact=True).click()
    expect(overview_edit).to_be_hidden()

    page.get_by_role("link", name="Wocheneinkauf").click()
    item = page.locator(".shopping-item", has_text="Tofu")
    expect(item.get_by_role("button", name="Move")).to_have_count(0)
    expect(item.get_by_role("button", name="Edit item")).to_have_count(0)
    expect(item.get_by_role("button", name="Toggle completed")).to_be_visible()
    expect(page.get_by_role("button", name="Add")).to_be_visible()
    expect(page.get_by_role("button", name="Edit", exact=True)).to_have_count(0)
    expect(page.get_by_role("link", name="Edit list")).to_be_visible()

    page.get_by_role("link", name="Recipes", exact=True).click()
    recipe_card = page.locator(".list-card", has_text=recipe_title)
    recipe_edit = recipe_card.get_by_role("link", name="Edit", exact=True, include_hidden=True)
    expect(recipe_edit).to_be_hidden()
    show_edit_actions(page)
    expect(recipe_edit).to_be_visible()

    page.get_by_role("link", name=recipe_title).click()
    line = page.locator(".recipe-line", has_text="Flour")
    expect(line.get_by_role("button")).to_have_count(0)
    expect(page.locator("#ingredient-form, #step-form")).to_have_count(0)
    expect(page.get_by_role("button", name="Add to a shopping list", exact=True)).to_be_visible()
    expect(page.get_by_role("link", name="Edit recipe", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Edit", exact=True)).to_have_count(0)


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_user_can_edit_a_list_from_the_overview(authenticated_page, user):
    from easy_kitchen.models import ShoppingList

    shopping_list = ShoppingList.objects.create(user=user, title="Alter Titel")
    page = authenticated_page
    page.reload()
    open_shopping_lists(page)
    card = page.locator(".list-card", has_text="Alter Titel")

    show_edit_actions(page)
    card.get_by_role("link", name="Edit", exact=True).click()
    page.locator("input[name=title]").fill("Neuer Titel")
    page.get_by_role("button", name="Save", exact=True).first.click()
    expect(page.get_by_role("heading", name="Shopping lists")).to_be_visible()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_user_can_edit_a_list_from_its_detail_page(authenticated_page, user):
    from easy_kitchen.models import ShoppingList

    shopping_list = ShoppingList.objects.create(user=user, title="Alter Titel")
    page = authenticated_page
    page.goto(f"{page.url.rstrip('/')}/lists/{shopping_list.pk}/")

    page.get_by_role("link", name="Edit list").click()
    page.locator("input[name=title]").fill("Neuer Titel")
    page.get_by_role("button", name="Save", exact=True).first.click()

    expect(page.get_by_role("heading", name="Neuer Titel")).to_be_visible()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_user_can_delete_a_list_from_the_overview_modal(authenticated_page, user):
    from easy_kitchen.models import ShoppingList

    ShoppingList.objects.create(user=user, title="Zu löschen")
    page = authenticated_page
    page.reload()
    open_shopping_lists(page)

    card = page.locator(".list-card", has_text="Zu löschen")
    show_edit_actions(page)
    card.get_by_role("button", name="Delete list").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    dialog.get_by_role("button", name="Delete permanently").click()
    expect(page.get_by_text("Zu löschen")).to_have_count(0)


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_user_can_reorder_lists_and_recipes_on_the_overview(authenticated_page, user):
    from easy_kitchen.models import ShoppingList
    from easy_kitchen.services import create_recipe

    older = ShoppingList.objects.create(user=user, title="Older list")
    newer = ShoppingList.objects.create(user=user, title="Newer list")
    first_recipe = create_recipe(user, title="First recipe")
    second_recipe = create_recipe(user, title="Second recipe")
    page = authenticated_page
    page.set_viewport_size({"width": 400, "height": 900})
    page.reload()
    open_shopping_lists(page)

    newer_handle = page.locator(f'[data-list-id="{newer.pk}"]').get_by_role("button", name="Move", include_hidden=True)
    older_handle = page.locator(f'[data-list-id="{older.pk}"]').get_by_role("button", name="Move", include_hidden=True)
    expect(newer_handle).to_be_hidden()
    show_edit_actions(page)
    with page.expect_response(lambda response: response.url.endswith("/lists/reorder/") and response.request.method == "POST"):
        newer_handle.drag_to(older_handle)
    page.reload()
    assert page.locator("#shopping-lists .list-card h2").all_text_contents() == ["Older list", "Newer list"]

    page.get_by_role("link", name="Recipes", exact=True).click()
    show_edit_actions(page)
    second_handle = page.locator(f'[data-list-id="{second_recipe.pk}"]').get_by_role("button", name="Move")
    first_handle = page.locator(f'[data-list-id="{first_recipe.pk}"]').get_by_role("button", name="Move")
    with page.expect_response(lambda response: response.url.endswith("/recipes/reorder/") and response.request.method == "POST"):
        second_handle.drag_to(first_handle)
    page.reload()
    assert page.locator("#recipes .list-card h2").all_text_contents() == ["First recipe", "Second recipe"]


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_user_can_reorder_items_with_drag_and_drop(authenticated_page, user):
    from easy_kitchen.models import ShoppingItem, ShoppingList

    shopping_list = ShoppingList.objects.create(user=user, title="Wocheneinkauf")
    ShoppingItem.objects.create(shopping_list=shopping_list, name="Tofu", position=1)
    ShoppingItem.objects.create(shopping_list=shopping_list, name="Reis", position=2)
    page = authenticated_page
    page.set_viewport_size({"width": 1280, "height": 1600})
    page.goto(f"{page.url.rstrip('/')}/lists/{shopping_list.pk}/")

    page.get_by_role("link", name="Edit list", exact=True).click()
    rows = page.locator('[data-editor-lines="items"] .editor-line')
    rows.first.get_by_role("button", name="Move", exact=True).drag_to(rows.last, target_position={"x": 20, "y": rows.last.bounding_box()["height"] - 5})
    expect(rows.first.get_by_label("Item", exact=True)).to_have_value("Reis")
    assert list(shopping_list.items.values_list("name", flat=True)) == ["Tofu", "Reis"]
    page.get_by_role("button", name="Save", exact=True).first.click()
    expect(page.get_by_role("heading", name="Wocheneinkauf", exact=True)).to_be_visible()
    assert page.locator(".shopping-item .item-name").all_text_contents() == ["Reis", "Tofu"]


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
    open_account_menu(page)

    page.get_by_role("link", name="Import JSON").click()
    expect(page.get_by_role("heading", name="Import JSON")).to_be_visible()
    page.locator("#id_json_data").fill(
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
    alert = page.get_by_role("alert")
    expect(alert).to_contain_text("Imported 1 shopping list.")
    expect(alert).to_be_hidden(timeout=5000)


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_user_can_export_selected_lists_and_recipes(authenticated_page, user):
    import json
    from datetime import date

    from easy_kitchen.services import create_recipe, create_shopping_list

    create_shopping_list(
        user,
        title="Weekend shop",
        date=date(2026, 11, 1),
        items=[{"name": "Apples", "quantity": "1 kg"}],
    )
    create_recipe(
        user,
        title="Pancakes",
        ingredients=[{"name": "Flour", "quantity": "200 g"}],
        steps=[{"text": "Mix the batter."}],
    )
    page = authenticated_page
    open_account_menu(page)
    page.get_by_role("link", name="Export JSON").click()
    expect(page.get_by_role("heading", name="Export JSON")).to_be_visible()
    page.get_by_label("Weekend shop").check()
    page.get_by_label("Pancakes").check()

    with page.expect_download() as download_info:
        page.get_by_role("button", name="Export").click()
    payload = json.loads(download_info.value.path().read_text())

    assert payload["lists"][0]["title"] == "Weekend shop"
    assert payload["lists"][0]["items"] == [{"name": "Apples", "quantity": "1 kg", "checked": False}]
    assert payload["recipes"][0]["title"] == "Pancakes"


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_user_can_save_calories_protein_and_preparation_time(authenticated_page):
    page = authenticated_page
    page.get_by_role("link", name="Recipes", exact=True).click()
    page.get_by_role("link", name="New recipe").click()
    page.get_by_label("Title").fill("Pancakes")
    page.get_by_label("Calories (kcal)").fill("450")
    page.get_by_label("Protein (g)").fill("12")
    page.get_by_label("Preparation time (min)").fill("25")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_role("heading", name="Pancakes")).to_be_visible()
    expect(page.get_by_text("450 kcal")).to_be_visible()
    expect(page.get_by_text("12 g protein")).to_be_visible()
    expect(page.get_by_text("25 min")).to_be_visible()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_clicking_a_recipe_picture_opens_the_recipe(authenticated_page, user):
    from easy_kitchen.services import create_recipe

    create_recipe(user, title="Pancakes")
    page = authenticated_page
    page.get_by_role("link", name="Recipes", exact=True).click()
    image = page.locator(".recipe-card-picture")
    expect(image).to_have_attribute("src", re.compile(r"recipe-placeholder\.svg$"))
    box = image.bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    expect(page.get_by_role("heading", name="Pancakes")).to_be_visible()
    expect(page.locator(".recipe-picture")).to_have_attribute("src", re.compile(r"recipe-placeholder\.svg$"))


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_user_can_edit_a_recipe_from_the_overview(authenticated_page, user):
    from easy_kitchen.services import create_recipe

    create_recipe(user, title="Alter Titel")
    page = authenticated_page
    page.get_by_role("link", name="Recipes", exact=True).click()
    card = page.locator(".list-card", has_text="Alter Titel")

    show_edit_actions(page)
    card.get_by_role("link", name="Edit", exact=True).click()
    page.get_by_label("Title").fill("Neuer Titel")
    page.get_by_role("button", name="Save", exact=True).first.click()

    expect(page.get_by_role("heading", name="Recipes")).to_be_visible()
    expect(page.get_by_role("link", name="Neuer Titel")).to_be_visible()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_user_can_edit_a_recipe_from_its_detail_page(authenticated_page, user):
    from easy_kitchen.services import create_recipe

    recipe = create_recipe(user, title="Alter Titel")
    page = authenticated_page
    page.goto(f"{page.url.rstrip('/')}/recipes/{recipe.pk}/")

    page.get_by_role("link", name="Edit recipe").click()
    page.get_by_label("Title").fill("Neuer Titel")
    page.get_by_role("button", name="Save", exact=True).first.click()

    expect(page.get_by_role("heading", name="Neuer Titel")).to_be_visible()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_recipe_ingredients_can_be_added_to_a_new_list(authenticated_page):
    page = authenticated_page
    page.get_by_role("link", name="Recipes", exact=True).click()
    page.get_by_role("link", name="New recipe").click()
    page.get_by_label("Title").fill("Pancakes")
    page.get_by_label("Description").fill("Sunday breakfast")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_role("heading", name="Pancakes")).to_be_visible()

    page.get_by_role("link", name="Edit recipe", exact=True).click()
    page.get_by_role("button", name="Add ingredient", exact=True).click()
    page.get_by_label("Ingredient", exact=True).fill("Flour")
    page.get_by_label("Quantity", exact=True).fill("200 g")
    page.get_by_role("button", name="Add step", exact=True).click()
    page.get_by_label("Step", exact=True).fill("Mix the batter")
    page.get_by_role("button", name="Save", exact=True).first.click()
    expect(page.locator("#ingredients")).to_contain_text("Flour")
    expect(page.locator("#steps")).to_contain_text("Mix the batter")

    page.get_by_role("button", name="Add to a shopping list", exact=True).click()
    page.get_by_role("dialog", name="Add to a shopping list", exact=True).get_by_label("New list").fill("Weekend")
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
        expect(swagger.get_by_text("EasyKitchen API")).to_be_visible()
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
