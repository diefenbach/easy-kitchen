from datetime import date

import pytest
from playwright.sync_api import expect

from easy_kitchen.models import MealPlanEntry
from easy_kitchen.services import create_recipe


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_weekly_planning_with_autocomplete_and_merged_shopping_list(authenticated_page, user, other_user):
    create_recipe(user, title="Onion soup", ingredients=[{"name": "Onion", "quantity": "2"}])
    create_recipe(user, title="Salad", ingredients=[{"name": "Onion", "quantity": "1"}])
    create_recipe(other_user, title="Private recipe")
    page = authenticated_page
    page.get_by_role("link", name="Meal planner", exact=True).click()
    expect(page.get_by_role("heading", name="Meal planner", exact=True)).to_be_visible()
    monday = page.locator(".planner-day").nth(0)
    search = monday.locator("input.recipe-search")
    search.fill("sOuP")
    expect(monday.get_by_role("option", name="Onion soup", exact=True)).to_be_visible()
    expect(page.get_by_role("option", name="Private recipe", exact=True)).to_have_count(0)
    search.press("ArrowDown")
    search.press("Enter")
    expect(search).to_have_value("Onion soup")
    monday.get_by_role("button", name="Save plan", exact=True).click()
    expect(monday.get_by_role("link", name="Onion soup", exact=True)).to_be_visible()
    expect(monday.locator(".planner-recipe-picture")).to_have_attribute("src", "/static/easy_kitchen/recipe-placeholder.svg")
    expect(monday.locator("input.recipe-search")).to_have_count(0)
    expect(monday.get_by_role("button", name="Save plan", exact=True)).to_have_count(0)

    tuesday = page.locator(".planner-day").nth(1)
    tuesday.locator("input.recipe-search").fill("sal")
    tuesday.get_by_role("option", name="Salad", exact=True).click()
    tuesday.get_by_role("button", name="Save plan", exact=True).click()
    expect(tuesday.get_by_role("link", name="Salad", exact=True)).to_be_visible()
    page.reload()
    expect(monday.get_by_role("link", name="Onion soup", exact=True)).to_be_visible()
    expect(tuesday.get_by_role("link", name="Salad", exact=True)).to_be_visible()
    expect(monday.locator("input.recipe-search")).to_have_count(0)
    expect(tuesday.locator("input.recipe-search")).to_have_count(0)

    page.get_by_label("New list", exact=True).fill("Weekly shop")
    page.get_by_role("button", name="Create shopping list", exact=True).click()
    expect(page.get_by_role("heading", name="Weekly shop", exact=True)).to_be_visible()
    expect(page.locator(".shopping-item", has_text="Onion").locator(".item-quantity")).to_have_text("3")


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_autocomplete_rejects_unselected_text_and_returns_after_clearing_a_day(
    authenticated_page, user, live_server
):
    week = date(2026, 12, 28)
    create_recipe(user, title="Soup")
    create_recipe(user, title="Salad")
    page = authenticated_page
    page.goto(f"{live_server.url}/planner/?week={week.isoformat()}")
    monday = page.locator(".planner-day").first
    search = monday.locator("input.recipe-search")
    search.fill("Does not exist")
    monday.get_by_role("button", name="Save plan", exact=True).click()
    assert not MealPlanEntry.objects.filter(user=user, date=week).exists()
    expect(search).to_have_value("Does not exist")

    search.fill("sou")
    search.press("Escape")
    expect(monday.get_by_role("listbox")).to_be_hidden()
    search.press("ArrowDown")
    search.press("Enter")
    monday.get_by_role("button", name="Save plan", exact=True).click()
    expect(monday.get_by_role("link", name="Soup", exact=True)).to_be_visible()
    expect(search).to_have_count(0)
    expect(monday.get_by_role("button", name="Save plan", exact=True)).to_have_count(0)
    page.reload()
    expect(monday.get_by_role("link", name="Soup", exact=True)).to_be_visible()
    expect(search).to_have_count(0)
    monday.get_by_role("button", name="Remove recipe from this day").click()
    expect(monday.get_by_text("No recipe planned", exact=True)).to_have_count(0)
    expect(search).to_be_visible()
    expect(search).to_have_value("")
    assert not MealPlanEntry.objects.filter(user=user, date=week).exists()
    search.fill("sal")
    monday.get_by_role("option", name="Salad", exact=True).click()
    monday.get_by_role("button", name="Save plan", exact=True).click()
    expect(monday.get_by_role("link", name="Salad", exact=True)).to_be_visible()
    expect(search).to_have_count(0)

    page.get_by_role("link", name="Next week", exact=True).click()
    expect(page).to_have_url(f"{live_server.url}/planner/?week=2027-01-04")
    page.get_by_role("link", name="Previous week", exact=True).click()
    expect(page).to_have_url(f"{live_server.url}/planner/?week=2026-12-28")


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_mobile_planner_selects_a_recipe_without_horizontal_overflow(authenticated_page, user):
    recipe = create_recipe(user, title="A very long recipe title for an easy weekday dinner")
    page = authenticated_page
    page.set_viewport_size({"width": 390, "height": 844})
    page.get_by_role("link", name="Meal planner", exact=True).click()
    day = page.locator(".planner-day").first
    day.locator("input.recipe-search").fill("weekday")
    day.get_by_role("option", name=recipe.title, exact=True).click()
    day.get_by_role("button", name="Save plan", exact=True).click()
    expect(day.get_by_role("link", name=recipe.title, exact=True)).to_be_visible()
    expect(day.locator("input.recipe-search")).to_have_count(0)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("width", [1280, 390])
def test_empty_day_recipe_selection_fills_the_available_width(authenticated_page, user, width):
    create_recipe(user, title="Soup")
    page = authenticated_page
    page.set_viewport_size({"width": width, "height": 844})
    page.get_by_role("link", name="Meal planner", exact=True).click()
    expect(page.get_by_text("No recipe planned", exact=True)).to_have_count(0)
    day = page.locator(".planner-day").first
    search = day.locator("input.recipe-search")
    form = search.locator("xpath=ancestor::form[1]")
    row = day.locator(":scope > div")
    date_column = day.get_by_text("Monday", exact=True).locator("..")
    save = day.get_by_role("button", name="Save plan", exact=True)
    row_box = row.bounding_box()
    date_box = date_column.bounding_box()
    form_box = form.bounding_box()
    search_box = search.bounding_box()
    save_box = save.bounding_box()
    assert abs(save_box["height"] - search_box["height"]) <= 1

    if width >= 768:
        assert 0 <= form_box["x"] - (date_box["x"] + date_box["width"]) <= 20
    else:
        assert abs(form_box["x"] - row_box["x"]) <= 1
    assert abs(form_box["x"] + form_box["width"] - row_box["x"] - row_box["width"]) <= 1
    assert search_box["width"] >= form_box["width"] - save_box["width"] - 10

    search.fill("sou")
    expect(day.get_by_role("option", name="Soup", exact=True)).to_be_visible()
    assert abs(day.get_by_role("listbox").bounding_box()["width"] - search_box["width"]) <= 1


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_duplicate_titles_select_the_chosen_recipe_id(authenticated_page, user):
    first = create_recipe(user, title="Soup")
    second = create_recipe(user, title="Soup")
    page = authenticated_page
    page.get_by_role("link", name="Meal planner", exact=True).click()
    day = page.locator(".planner-day").first
    day.locator("input.recipe-search").fill("soup")
    choices = day.get_by_role("option", name="Soup", exact=True)
    expect(choices).to_have_count(2)
    choices.nth(1).click()
    day.get_by_role("button", name="Save plan", exact=True).click()
    entry = MealPlanEntry.objects.get(user=user)
    assert entry.recipe_id == max(first.pk, second.pk)


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_planner_searches_only_titles_and_combines_terms(authenticated_page, user, other_user):
    recipe = create_recipe(
        user,
        title="Weeknight bowl",
        description="Cremiges Sommergericht",
        ingredients=[{"name": "Kichererbsen", "quantity": "200 g"}],
        steps=[{"text": "Zuerst rösten, danach pürieren."}],
    )
    create_recipe(user, title="Kichererbsen Suppe")
    create_recipe(other_user, title="Private bowl", description="Geheime Zutat")
    page = authenticated_page
    page.get_by_role("link", name="Meal planner", exact=True).click()
    day = page.locator(".planner-day").first
    search = day.locator("input.recipe-search")

    for query in ("BOWL", "weeknight", "  BOWL   weekNIGHT  "):
        search.fill(query)
        expect(day.get_by_role("option", name=recipe.title, exact=True)).to_be_visible()

    expect(day.get_by_role("option", name="Kichererbsen Suppe", exact=True)).to_have_count(0)
    for query in ("Sommer", "pÜrieren", "200", "bowl Kichererbsen", "bowl Erdbeeren", "Geheime Zutat"):
        search.fill(query)
        expect(day.get_by_role("option")).to_have_count(0)

    search.fill("bowl weeknight")
    search.press("ArrowDown")
    search.press("Enter")
    day.get_by_role("button", name="Save plan", exact=True).click()
    expect(day.get_by_role("link", name=recipe.title, exact=True)).to_be_visible()
    assert MealPlanEntry.objects.get(user=user).recipe_id == recipe.pk


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("width", [1280, 390])
def test_recipe_suggestions_show_pictures_on_the_left(authenticated_page, user, live_server, width):
    picture_url = f"{live_server.url}/static/easy_kitchen/logo.png"
    title = "Soup with a picture and a long title for a relaxed weekday dinner"
    create_recipe(user, title=title, image_url=picture_url)
    create_recipe(user, title="Soup without a picture")
    create_recipe(user, title="Soup with a missing picture", image_url=f"{live_server.url}/missing.png")
    page = authenticated_page
    page.set_viewport_size({"width": width, "height": 844})
    page.get_by_role("link", name="Meal planner", exact=True).click()
    day = page.locator(".planner-day").first
    search = day.locator("input.recipe-search")
    search.fill("soup")
    pictured = day.get_by_role("option", name=title, exact=True)
    picture = pictured.locator("img")
    expect(picture).to_be_visible()
    expect(picture).to_have_attribute("src", picture_url)
    expect(picture).to_have_js_property("complete", True)
    assert picture.evaluate("image => image.naturalWidth > 0")
    picture_box = picture.bounding_box()
    assert abs(picture_box["width"] - 96) <= 1
    assert abs(picture_box["height"] - 96) <= 1
    title_box = pictured.get_by_text(title, exact=True).bounding_box()
    assert picture_box["x"] + picture_box["width"] < title_box["x"]

    for name in ("Soup without a picture", "Soup with a missing picture"):
        fallback = day.get_by_role("option", name=name, exact=True).locator("img")
        expect(fallback).to_have_attribute("src", "/static/easy_kitchen/recipe-placeholder.svg")
        expect(fallback).to_have_js_property("complete", True)
        assert fallback.evaluate("image => image.naturalWidth > 0")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

    picture.click()
    expect(search).to_have_value(title)
    day.get_by_role("button", name="Save plan", exact=True).click()
    expect(day.get_by_role("link", name=title, exact=True)).to_be_visible()

    selected_picture = day.locator(".planner-recipe-picture")
    expect(selected_picture).to_be_visible()
    expect(selected_picture).to_have_attribute("src", picture_url)
    link = day.locator(".planner-recipe-title")
    expect(link).to_have_css("text-decoration-line", "none")
    assert abs(link.bounding_box()["y"] - selected_picture.bounding_box()["y"]) <= 1
    if width >= 768:
        picture_top = selected_picture.bounding_box()["y"]
        date_column = day.get_by_text("Monday", exact=True).locator("..")
        remove = day.get_by_role("button", name="Remove recipe from this day")
        assert abs(date_column.bounding_box()["y"] - picture_top) <= 1
        assert abs(remove.bounding_box()["y"] - picture_top) <= 1
    assert link.evaluate("element => getComputedStyle(element).color === getComputedStyle(element.closest('.planner-day')).color")
    link.hover()
    expect(link).to_have_css("text-decoration-line", "none")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    selected_picture.click()
    expect(page.get_by_role("heading", name=title, exact=True)).to_be_visible()
    page.go_back()
    day.locator(".planner-recipe-title").click()
    expect(page.get_by_role("heading", name=title, exact=True)).to_be_visible()
