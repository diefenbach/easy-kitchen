import io

import pytest
from PIL import Image
from playwright.sync_api import expect

from easy_kitchen.models import Recipe
from easy_kitchen.services import create_recipe


def open_modal(page, trigger, modal_id):
    page.locator(f"#{modal_id}").evaluate("""element => {
        window.editorModalShown = new Promise(resolve => {
            element.addEventListener('shown.bs.modal', () => resolve(), {once: true});
        });
    }""")
    trigger.click()
    page.evaluate("window.editorModalShown")


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("width", [1280, 390])
def test_whole_recipe_editor_saves_draft_and_cancel_discards_it(authenticated_page, user, live_server, width):
    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Onion", "quantity": "1"}, {"name": "Carrot"}], steps=["Chop", "Simmer"])
    onion_id = recipe.ingredients.first().pk
    page = authenticated_page
    page.set_viewport_size({"width": width, "height": 844})
    detail = f"{live_server.url}/recipes/{recipe.pk}/"
    page.goto(detail)
    page.evaluate("window.scrollTo({top: 0, behavior: 'instant'}); window.editorPageSentinel = 'same-document'")
    scroll_y = page.evaluate("window.scrollY")
    expect(page.locator("#ingredients").get_by_role("button")).to_have_count(0)
    page.get_by_role("link", name="Edit recipe", exact=True).click()
    expect(page.get_by_role("heading", name="Edit recipe", exact=True)).to_be_visible()
    expect(page).to_have_url(detail + "edit/")
    assert abs(page.evaluate("window.scrollY") - scroll_y) < 1
    assert page.evaluate("window.editorPageSentinel") == "same-document"
    page.get_by_label("Title", exact=True).fill("Discarded title")
    ingredients = page.locator('[data-editor-lines="ingredients"]')
    ingredients.locator(".editor-line").first.get_by_role("button", name="Remove ingredient", exact=True).click()
    page.get_by_role("link", name="Cancel", exact=True).first.click()
    expect(page).to_have_url(detail)
    assert page.evaluate("window.editorPageSentinel") == "same-document"
    expect(page.get_by_role("heading", name="Soup", exact=True)).to_be_visible()
    assert recipe.ingredients.count() == 2
    page.get_by_role("link", name="Edit recipe", exact=True).click()
    page.get_by_label("Title", exact=True).fill("New soup")
    page.get_by_label("Description", exact=True).fill("A complete recipe")
    page.get_by_label("Calories (kcal)", exact=True).fill("250")
    rows = ingredients.locator(".editor-line:not([hidden])")
    rows.first.get_by_label("Ingredient", exact=True).fill("Red onion")
    rows.first.get_by_label("Quantity", exact=True).fill("2")
    rows.nth(1).get_by_role("button", name="Remove ingredient", exact=True).click()
    ingredients.get_by_role("button", name="Add ingredient", exact=True).click()
    rows.last.get_by_label("Ingredient", exact=True).fill("Salt")
    rows.last.get_by_label("Quantity", exact=True).fill("1 tsp")
    rows.last.get_by_role("button", name="Move up", exact=True).click()
    steps = page.locator('[data-editor-lines="steps"]')
    steps.locator(".editor-line").first.get_by_label("Step", exact=True).fill("Chop finely")
    steps.locator(".editor-line").last.get_by_role("button", name="Move up", exact=True).click()
    steps.get_by_role("button", name="Add step", exact=True).click()
    steps.locator(".editor-line").last.get_by_label("Step", exact=True).fill("Serve")
    assert Recipe.objects.get(pk=recipe.pk).title == "Soup"
    assert list(recipe.ingredients.values_list("name", flat=True)) == ["Onion", "Carrot"]
    footer = page.locator(".recipe-editor-footer")
    expect(footer).to_have_css("position", "sticky")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.get_by_role("button", name="Save", exact=True).last.click()
    expect(page).to_have_url(detail)
    expect(page.get_by_role("heading", name="New soup", exact=True)).to_be_visible()
    assert page.evaluate("window.editorPageSentinel") == "same-document"
    recipe.refresh_from_db()
    assert recipe.description == "A complete recipe" and recipe.calories == 250
    assert list(recipe.ingredients.values_list("name", "quantity")) == [("Salt", "1 tsp"), ("Red onion", "2")]
    assert recipe.ingredients.get(name="Red onion").pk == onion_id
    assert list(recipe.steps.values_list("text", flat=True)) == ["Simmer", "Chop finely", "Serve"]
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_editor_errors_keep_all_draft_sections_visible(authenticated_page, user, live_server):
    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Onion"}], steps=["Chop"])
    page = authenticated_page
    page.goto(f"{live_server.url}/recipes/{recipe.pk}/edit/")
    page.get_by_label("Title", exact=True).fill("")
    page.get_by_label("Description", exact=True).fill("Draft description")
    page.locator("#recipe-editor-form").evaluate("form => { form.noValidate = true; }")
    page.get_by_role("button", name="Save", exact=True).first.click()
    expect(page.get_by_role("alert")).to_contain_text("Your changes have not been saved.")
    expect(page.get_by_label("Description", exact=True)).to_have_value("Draft description")
    expect(page.get_by_label("Ingredient", exact=True)).to_be_visible()
    expect(page.get_by_label("Ingredient", exact=True)).to_have_value("Onion")
    expect(page.get_by_label("Step", exact=True)).to_be_visible()
    assert Recipe.objects.get(pk=recipe.pk).description == ""
    page.get_by_label("Title", exact=True).fill("Valid soup")
    page.get_by_role("button", name="Save", exact=True).last.click()
    expect(page.get_by_role("heading", name="Valid soup", exact=True)).to_be_visible()
    assert Recipe.objects.get(pk=recipe.pk).description == "Draft description"


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_editor_history_direct_links_and_recipe_modals_after_save(authenticated_page, user, live_server):
    recipe = create_recipe(user, title="Soup", steps=["Chop"])
    page = authenticated_page
    detail = f"{live_server.url}/recipes/{recipe.pk}/"
    editor_url = detail + "edit/"
    page.goto(detail)
    page.evaluate("window.editorHistorySentinel = true")
    page.get_by_role("link", name="Edit recipe", exact=True).click()
    expect(page).to_have_url(editor_url)
    page.get_by_role("link", name="Cancel", exact=True).first.click()
    expect(page).to_have_url(detail)
    page.go_back()
    expect(page).to_have_url(editor_url)
    expect(page.get_by_role("heading", name="Edit recipe", exact=True)).to_be_visible()
    page.get_by_role("button", name="Add ingredient", exact=True).click()
    page.get_by_label("Ingredient", exact=True).fill("Onion")
    page.get_by_role("button", name="Save", exact=True).first.click()
    expect(page).to_have_url(detail)
    expect(page.locator("#ingredients")).to_contain_text("Onion")
    assert page.evaluate("window.editorHistorySentinel") is True
    open_modal(page, page.get_by_role("button", name="Plan recipe", exact=True), "add-to-planner-modal")
    modal = page.get_by_role("dialog", name="Add to meal planner", exact=True)
    expect(modal).to_be_visible()
    modal.get_by_role("button", name="Cancel", exact=True).click()
    expect(modal).to_be_hidden()
    page.get_by_role("link", name="Edit recipe", exact=True).click()
    expect(page).to_have_url(editor_url)
    expect(page.get_by_role("heading", name="Edit recipe", exact=True)).to_be_visible()
    page.reload()
    expect(page.get_by_role("heading", name="Edit recipe", exact=True)).to_be_visible()
    picture = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(picture, format="PNG")
    page.get_by_label("Image", exact=True).set_input_files({"name": "recipe.png", "mimeType": "image/png", "buffer": picture.getvalue()})
    page.get_by_role("button", name="Add step", exact=True).click()
    page.locator('[data-editor-lines="steps"] .editor-line').last.get_by_label("Step", exact=True).fill("Simmer")
    page.get_by_role("button", name="Save", exact=True).first.click()
    expect(page).to_have_url(detail)
    expect(page.locator("#steps")).to_contain_text("Simmer")
    recipe.refresh_from_db()
    assert recipe.image
    expect(page.locator(".recipe-picture")).to_have_attribute("src", recipe.image.url)
    page.get_by_role("button", name="Add to a shopping list", exact=True).click()
    expect(page.get_by_role("dialog", name="Add to a shopping list", exact=True)).to_be_visible()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("width", [1280, 390])
@pytest.mark.parametrize("scroll_y", [0, 80])
def test_opening_editor_preserves_scroll_with_normal_browser_styles(authenticated_page, user, live_server, width, scroll_y):
    recipe = create_recipe(user, title="A long recipe title for a weekday dinner", description="Recipe description", ingredients=[{"name": "Onion"}], steps=["Chop", "Cook"])
    page = authenticated_page
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(f"{live_server.url}/recipes/{recipe.pk}/")
    page.evaluate("y => window.scrollTo({top: y, behavior: 'instant'})", scroll_y)
    before = page.evaluate("window.scrollY")
    page.get_by_role("link", name="Edit recipe", exact=True).click()
    expect(page.get_by_role("heading", name="Edit recipe", exact=True)).to_be_visible()
    expect(page).to_have_url(f"{live_server.url}/recipes/{recipe.pk}/edit/")
    page.wait_for_function("!document.querySelector('.htmx-settling')")
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
    assert abs(page.evaluate("window.scrollY") - before) < 1
    assert page.evaluate("document.documentElement.style.overflowAnchor") == ""
    assert page.evaluate("document.documentElement.style.scrollBehavior") == ""


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("width", [1280, 390])
@pytest.mark.parametrize("scroll_y", [0, 80])
@pytest.mark.parametrize("action", ["save", "cancel"])
def test_saving_and_cancelling_editor_preserve_scroll(authenticated_page, user, live_server, width, scroll_y, action):
    recipe = create_recipe(user, title="Soup", description="Recipe description", ingredients=[{"name": "Onion"}], steps=[f"Preparation step {index}" for index in range(12)])
    page = authenticated_page
    page.set_viewport_size({"width": width, "height": 844})
    detail = f"{live_server.url}/recipes/{recipe.pk}/"
    page.goto(detail + "edit/")
    page.get_by_label("Title", exact=True).fill("Updated soup")
    page.evaluate("y => window.scrollTo({top: y, behavior: 'instant'})", scroll_y)
    before = page.evaluate("window.scrollY")
    if action == "save":
        page.get_by_role("button", name="Save", exact=True).first.click()
    else:
        page.get_by_role("link", name="Cancel", exact=True).first.click()
    expect(page).to_have_url(detail)
    expect(page.get_by_role("heading", name="Updated soup" if action == "save" else "Soup", exact=True)).to_be_visible()
    page.wait_for_function("!document.querySelector('.htmx-settling')")
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
    assert abs(page.evaluate("window.scrollY") - before) < 1
    assert page.evaluate("document.documentElement.style.overflowAnchor") == ""
    assert page.evaluate("document.documentElement.style.scrollBehavior") == ""


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("width", [1280, 390])
def test_recipe_delete_is_in_editor_and_requires_confirmation(authenticated_page, user, live_server, width):
    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Onion"}], steps=["Chop"])
    page = authenticated_page
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(f"{live_server.url}/recipes/{recipe.pk}/")
    expect(page.get_by_role("button", name="Delete", exact=True)).to_have_count(0)
    page.get_by_role("link", name="Edit recipe", exact=True).click()
    page.get_by_label("Title", exact=True).fill("Unsaved title")
    open_modal(page, page.get_by_role("button", name="Delete", exact=True), "delete-recipe-modal")
    modal = page.get_by_role("dialog", name="Delete recipe?", exact=True)
    expect(modal).to_be_visible()
    modal.get_by_role("button", name="Cancel", exact=True).click()
    expect(modal).to_be_hidden()
    expect(page.get_by_label("Title", exact=True)).to_have_value("Unsaved title")
    assert Recipe.objects.get(pk=recipe.pk).title == "Soup"
    dialogs = []
    def accept_dialog(dialog):
        dialogs.append(dialog.type)
        dialog.accept()
    page.on("dialog", accept_dialog)
    open_modal(page, page.get_by_role("button", name="Delete", exact=True), "delete-recipe-modal")
    modal.get_by_role("button", name="Delete permanently", exact=True).click()
    expect(page).to_have_url(f"{live_server.url}/recipes/")
    expect(page.get_by_role("heading", name="Recipes", exact=True)).to_be_visible()
    assert not Recipe.objects.filter(pk=recipe.pk).exists()
    assert dialogs == []


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_editor_back_and_forward_confirm_before_discarding(authenticated_page, user, live_server):
    recipe = create_recipe(user, title="Soup", steps=["Chop"])
    page = authenticated_page
    detail = f"{live_server.url}/recipes/{recipe.pk}/"
    page.goto(detail)
    page.get_by_role("link", name="Edit recipe", exact=True).click()
    title = page.get_by_label("Title", exact=True)
    title.fill("Draft soup")
    dialogs = []

    def dismiss(dialog):
        dialogs.append(dialog.message)
        dialog.dismiss()

    page.on("dialog", dismiss)
    page.evaluate("history.back()")
    expect(page).to_have_url(detail + "edit/")
    expect(title).to_have_value("Draft soup")
    assert len(dialogs) == 1
    page.remove_listener("dialog", dismiss)
    page.once("dialog", lambda dialog: dialog.accept())
    page.evaluate("history.back()")
    expect(page).to_have_url(detail)
    expect(page.get_by_role("heading", name="Soup", exact=True)).to_be_visible()
    page.evaluate("history.forward()")
    expect(title).to_have_value("Soup")
    page.get_by_role("link", name="Cancel", exact=True).first.click()
    expect(page).to_have_url(detail)
    page.evaluate("history.back()")
    expect(title).to_have_value("Soup")
    title.fill("Another draft")
    page.on("dialog", dismiss)
    page.evaluate("history.forward()")
    expect(page).to_have_url(detail + "edit/")
    expect(title).to_have_value("Another draft")
    assert len(dialogs) == 2
    page.remove_listener("dialog", dismiss)
    page.once("dialog", lambda dialog: dialog.accept())
    page.evaluate("history.forward()")
    expect(page).to_have_url(detail)
    recipe.refresh_from_db()
    assert recipe.title == "Soup"
