import re

import pytest
from playwright.sync_api import expect

from easy_kitchen.models import Recipe
from easy_kitchen.services import create_recipe


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("width", [1280, 390])
def test_recipe_search_and_favorites_flow(authenticated_page, user, other_user, live_server, width):
    soup = create_recipe(user, title="Tomato soup", description="Summer dinner")
    create_recipe(user, title="Salad", description="Summer lunch")
    create_recipe(other_user, title="Private summer recipe")
    page = authenticated_page
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(f"{live_server.url}/recipes/")
    search = page.get_by_role("searchbox", name="Search recipes", exact=True)
    search.fill("SUMMER")
    page.get_by_role("button", name="Search", exact=True).click()
    expect(page.get_by_role("link", name="Tomato soup", exact=True)).to_be_visible()
    expect(page.get_by_role("link", name="Salad", exact=True)).to_be_visible()
    expect(page.get_by_role("link", name="Private summer recipe", exact=True)).to_have_count(0)
    card = page.locator("article", has=page.get_by_role("link", name="Tomato soup", exact=True))
    expect(card.get_by_role("button", name="Add to favorites", exact=True).locator("i")).to_have_class("bi bi-heart")
    card.get_by_role("button", name="Add to favorites", exact=True).click()
    expect(card.get_by_role("button", name="Remove from favorites", exact=True)).to_have_attribute("aria-pressed", "true")
    expect(search).to_have_value("SUMMER")
    page.reload()
    expect(card.get_by_role("button", name="Remove from favorites", exact=True)).to_be_visible()
    page.get_by_role("checkbox", name="Favorites only", exact=True).check()
    expect(page).to_have_url(re.compile(r"favorites=1"))
    expect(page.get_by_role("link", name="Salad", exact=True)).to_have_count(0)
    expect(card).to_be_visible()
    card.get_by_role("button", name="Remove from favorites", exact=True).click()
    expect(page.get_by_role("heading", name="No matching recipes", exact=True)).to_be_visible()
    expect(search).to_have_value("SUMMER")
    expect(page.get_by_role("checkbox", name="Favorites only", exact=True)).to_be_checked()
    page.get_by_role("link", name="Reset filters", exact=True).click()
    expect(page.get_by_role("link", name="Salad", exact=True)).to_be_visible()
    page.get_by_role("link", name="Tomato soup", exact=True).click()
    favorite = page.get_by_role("button", name="Add to favorites", exact=True)
    expect(page.locator("#recipe-actions").get_by_role("button", name="Add to favorites", exact=True)).to_have_count(0)
    image_box = page.locator(".recipe-picture").bounding_box()
    favorite_box = favorite.bounding_box()
    assert favorite_box["x"] >= image_box["x"]
    assert favorite_box["y"] >= image_box["y"]
    assert favorite_box["x"] + favorite_box["width"] <= image_box["x"] + image_box["width"]
    assert favorite_box["y"] + favorite_box["height"] <= image_box["y"] + image_box["height"]
    assert image_box["x"] + image_box["width"] - favorite_box["x"] - favorite_box["width"] < 20
    assert favorite_box["y"] - image_box["y"] < 20
    page.get_by_role("button", name="Add to favorites", exact=True).click()
    expect(page).to_have_url(f"{live_server.url}/recipes/{soup.pk}/")
    expect(page.get_by_role("button", name="Remove from favorites", exact=True)).to_have_attribute("aria-pressed", "true")
    expect(page.get_by_role("button", name="Remove from favorites", exact=True).locator("i")).to_have_class("bi bi-heart-fill")
    page.get_by_role("button", name="Remove from favorites", exact=True).click()
    expect(page.get_by_role("button", name="Add to favorites", exact=True)).to_have_attribute("aria-pressed", "false")
    assert not Recipe.objects.get(pk=soup.pk).is_favorite
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
