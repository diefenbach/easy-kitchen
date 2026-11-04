import pytest
from playwright.sync_api import expect

from easy_kitchen.models import MealPlanEntry, ShoppingList
from easy_kitchen.services import create_recipe


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("width", [1280, 390])
def test_recipe_detail_can_plan_a_recipe_using_a_date_modal(authenticated_page, user, live_server, width):
    recipe = create_recipe(user, title="Soup")
    page = authenticated_page
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(f"{live_server.url}/recipes/{recipe.pk}/")
    trigger = page.get_by_role("button", name="Plan recipe", exact=True)
    toolbar = page.get_by_role("group", name="Recipe actions", exact=True)
    edit = toolbar.get_by_role("button", name="Edit", exact=True)
    pdf = page.get_by_role("link", name="Download PDF", exact=True)
    actions = page.locator("#recipe-actions")
    shopping = actions.get_by_role("button", name="Add to a shopping list", exact=True)
    pdf_box = pdf.bounding_box()
    actions_box = actions.bounding_box()
    assert abs(pdf_box["x"] + pdf_box["width"] - actions_box["x"] - actions_box["width"]) <= 1
    assert pdf_box["x"] > shopping.bounding_box()["x"]
    for action in (trigger, shopping, pdf):
        if width < 768:
            expect(action.locator("span")).to_be_hidden()
        else:
            expect(action.locator("span")).to_be_visible()
    expect(toolbar.get_by_role("button", name="Plan recipe", exact=True)).to_have_count(0)
    expect(toolbar.get_by_role("link", name="Download PDF", exact=True)).to_have_count(0)
    back = page.locator(".list-back-button").bounding_box()
    assert actions_box["x"] > back["x"] + back["width"]
    assert abs(actions_box["y"] + actions_box["height"] / 2 - back["y"] - back["height"] / 2) <= 1
    assert actions_box["y"] < page.locator("header").bounding_box()["y"]
    assert float(edit.evaluate("element => getComputedStyle(element).borderTopRightRadius").rstrip("px")) > 0
    trigger.click()
    modal = page.get_by_role("dialog", name="Add to meal planner", exact=True)
    expect(modal).to_be_visible()
    date_input = modal.get_by_label("Date", exact=True)
    expect(date_input).to_have_attribute("type", "date")
    modal.get_by_role("button", name="Add to planner", exact=True).click()
    expect(modal).to_be_visible()
    assert not MealPlanEntry.objects.filter(user=user).exists()
    modal.get_by_role("button", name="Cancel", exact=True).click()
    expect(modal).to_be_hidden()
    assert not MealPlanEntry.objects.filter(user=user).exists()
    edit.click()
    expect(trigger).to_be_visible()
    expect(pdf).to_be_visible()
    remove = toolbar.get_by_role("button", name="Delete", exact=True)
    expect(remove).to_be_visible()
    expect(remove).to_have_css("border-top-left-radius", "0px")
    assert float(remove.evaluate("element => getComputedStyle(element).borderTopRightRadius").rstrip("px")) > 0
    toolbar.get_by_role("button", name="Done", exact=True).click()
    trigger.click()
    date_input.fill("2027-01-06")
    modal.get_by_role("button", name="Add to planner", exact=True).click()
    expect(page).to_have_url(f"{live_server.url}/planner/?week=2027-01-04")
    expect(page.locator(".planner-day").nth(2).get_by_role("link", name="Soup", exact=True)).to_be_visible()
    expect(page.locator('[role="alert"]')).to_have_count(0)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("width", [1280, 390])
@pytest.mark.parametrize("use_existing", [False, True])
def test_recipe_shopping_list_form_opens_in_a_modal(
    authenticated_page, user, live_server, width, use_existing
):
    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Onion", "quantity": "2"}])
    target = ShoppingList.objects.create(user=user, title="Weekly shop") if use_existing else None
    page = authenticated_page
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(f"{live_server.url}/recipes/{recipe.pk}/")
    trigger = page.get_by_role("button", name="Add to a shopping list", exact=True)
    trigger.click()
    modal = page.get_by_role("dialog", name="Add to a shopping list", exact=True)
    expect(modal).to_be_visible()
    modal.get_by_role("button", name="Cancel", exact=True).click()
    expect(modal).to_be_hidden()
    assert not recipe.user.shopping_lists.exclude(pk=target.pk if target else None).exists()

    trigger.click()
    modal.get_by_role("button", name="Add to list", exact=True).click()
    expect(modal).to_be_visible()
    expect(modal.get_by_text("Choose a list or enter a title for a new one.", exact=True)).to_be_visible()
    expect(page.get_by_role("dialog", name="Add to meal planner", exact=True)).to_be_hidden()
    if use_existing:
        modal.get_by_label("Shopping list", exact=True).select_option(str(target.pk))
    else:
        modal.get_by_label("New list", exact=True).fill("Weekly shop")
    modal.get_by_role("button", name="Add to list", exact=True).click()
    expect(page.get_by_role("heading", name="Weekly shop", exact=True)).to_be_visible()
    expect(page.locator(".shopping-item", has_text="Onion").locator(".item-quantity")).to_have_text("2")
    assert ShoppingList.objects.filter(user=user).count() == 1
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("width", [1280, 390])
def test_recipe_overview_image_actions_use_the_chosen_recipe(authenticated_page, user, live_server, width):
    soup = create_recipe(user, title="Soup", ingredients=[{"name": "Onion", "quantity": "2"}])
    salad = create_recipe(user, title="Salad", ingredients=[{"name": "Tomato", "quantity": "3"}])
    page = authenticated_page
    page.set_viewport_size({"width": width, "height": 844})
    overview_url = f"{live_server.url}/recipes/"
    page.goto(overview_url)
    soup_card = page.locator(f'#recipes [data-list-id="{soup.pk}"]')
    salad_card = page.locator(f'#recipes [data-list-id="{salad.pk}"]')
    image_box = soup_card.locator(".recipe-card-picture").bounding_box()
    actions_box = soup_card.locator(".recipe-card-actions").bounding_box()
    assert 0 <= actions_box["y"] - image_box["y"] <= 20
    assert 0 <= image_box["x"] + image_box["width"] - actions_box["x"] - actions_box["width"] <= 20

    soup_card.get_by_role("button", name="Plan recipe", exact=True).click()
    planner = page.get_by_role("dialog", name="Add to meal planner", exact=True)
    expect(planner).to_be_visible()
    expect(planner.locator("[data-recipe-title]")).to_have_text("Soup")
    expect(page).to_have_url(overview_url)
    planner.get_by_label("Date", exact=True).fill("2027-01-05")
    planner.get_by_role("button", name="Cancel", exact=True).click()
    expect(planner).to_be_hidden()
    salad_card.get_by_role("button", name="Plan recipe", exact=True).click()
    expect(planner.locator("[data-recipe-title]")).to_have_text("Salad")
    expect(planner.get_by_label("Date", exact=True)).to_have_value("")
    planner.get_by_label("Date", exact=True).fill("2027-01-06")
    planner.get_by_role("button", name="Add to planner", exact=True).click()
    expect(page).to_have_url(f"{live_server.url}/planner/?week=2027-01-04")
    assert MealPlanEntry.objects.get(user=user).recipe_id == salad.pk

    page.goto(overview_url)
    soup_card.get_by_role("button", name="Add to a shopping list", exact=True).click()
    shopping = page.get_by_role("dialog", name="Add to a shopping list", exact=True)
    expect(shopping.locator("[data-recipe-title]")).to_have_text("Soup")
    expect(page).to_have_url(overview_url)
    shopping.get_by_label("New list", exact=True).fill("Soup shop")
    shopping.get_by_role("button", name="Add to list", exact=True).click()
    expect(page.get_by_role("heading", name="Soup shop", exact=True)).to_be_visible()
    target = ShoppingList.objects.get(user=user, title="Soup shop")
    assert list(target.items.values_list("name", "quantity")) == [("Onion", "2")]
    page.goto(overview_url)
    expect(soup_card.get_by_role("button", name="Plan recipe", exact=True)).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
