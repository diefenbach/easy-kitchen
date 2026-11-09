import re
from datetime import timedelta

import pytest
from django.utils import timezone
from playwright.sync_api import expect

from easy_kitchen.models import MealPlanEntry, Recipe
from easy_kitchen.services import week_start_for


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("width", [1280, 390])
def test_home_actions_stay_grouped_at_right(authenticated_page, width):
    page = authenticated_page
    page.set_viewport_size({"width": width, "height": 844})
    main = page.locator("main")
    for heading, create, navigation in [
        ("Shopping lists", "New list", "See all lists"),
        ("Recipes", "New recipe", "See all recipes"),
        ("Planned meals this week", None, "View meal planner"),
        ("Planned meals next week", None, "View meal planner"),
    ]:
        title = main.get_by_role("heading", name=heading, exact=True)
        nav = title.locator("xpath=ancestor::section").get_by_role("link", name=navigation, exact=True)
        expect(nav).to_have_class(re.compile(r"btn btn-outline-secondary"))
        title_box, nav_box = title.bounding_box(), nav.bounding_box()
        section_box = title.locator("xpath=ancestor::section").bounding_box()
        assert abs(nav_box["x"] + nav_box["width"] - section_box["x"] - section_box["width"]) < 2
        assert title_box["y"] < nav_box["y"] + nav_box["height"]
        assert nav_box["y"] < title_box["y"] + title_box["height"]
        if create:
            action = main.get_by_role("link", name=create, exact=True)
            action_box = action.bounding_box()
            assert action_box["x"] > title_box["x"] + title_box["width"]
            assert abs(nav_box["x"] - action_box["x"] - action_box["width"] - 8) < 2
            assert abs(action_box["y"] - nav_box["y"]) < 2
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    main.get_by_role("link", name="See all recipes", exact=True).click()
    expect(page).to_have_url(re.compile(r"/recipes/$"))


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_home_next_week_meal_and_planner_link(authenticated_page, user):
    page = authenticated_page
    next_monday = week_start_for(timezone.localdate()) + timedelta(days=7)
    recipe = Recipe.objects.create(user=user, title="Next week dinner")
    MealPlanEntry.objects.create(user=user, date=next_monday, recipe=recipe)
    page.reload()
    section = page.locator("#home-next-week-meal-plan")
    expect(section.get_by_role("link", name="Next week dinner", exact=True)).to_be_visible()
    section.get_by_role("link", name="View meal planner", exact=True).click()
    expect(page).to_have_url(re.compile(rf"/planner/\?week={next_monday.isoformat()}$"))
