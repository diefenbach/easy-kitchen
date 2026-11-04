import json
import re
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.db import IntegrityError
from django.urls import reverse
from django.utils import translation

from easy_kitchen.models import MealPlanEntry, ShoppingList
from easy_kitchen.services import (
    add_meal_plan_week_to_list,
    create_item,
    create_recipe,
    set_meal_plan_recipe,
    week_start_for,
)


@pytest.mark.django_db
def test_planner_week_view_lists_seven_days(client, user):
    client.force_login(user)
    week = week_start_for(date(2026, 11, 3))  # Monday

    content = client.get(reverse("easy_kitchen:planner"), {"week": week.isoformat()}).content.decode()

    assert "Meal planner" in content
    assert "Create shopping list from plan" in content
    assert "No recipe planned" not in content
    assert content.count('name="recipe"') == 7


@pytest.mark.django_db
def test_user_can_assign_clear_and_build_list_from_plan(client, user):
    client.force_login(user)
    week = week_start_for(date(2026, 11, 3))
    soup = create_recipe(
        user,
        title="Soup",
        ingredients=[{"name": "Onion", "quantity": "1"}, {"name": "Stock", "quantity": "1 l"}],
    )
    salad = create_recipe(
        user,
        title="Salad",
        ingredients=[{"name": "Onion", "quantity": "2"}, {"name": "Tomato", "quantity": "3"}],
    )
    client.force_login(user)

    monday = week
    client.post(
        reverse("easy_kitchen:planner-assign"),
        {"week_start": week.isoformat(), "date": monday.isoformat(), "recipe": soup.pk},
    )
    client.post(
        reverse("easy_kitchen:planner-assign"),
        {"week_start": week.isoformat(), "date": (week + timedelta(days=2)).isoformat(), "recipe": salad.pk},
    )

    wednesday = week + timedelta(days=2)
    assert MealPlanEntry.objects.filter(user=user, date=monday, recipe=soup).exists()
    assert MealPlanEntry.objects.filter(user=user, date=wednesday, recipe=salad).exists()

    client.post(
        reverse("easy_kitchen:planner-clear", args=[monday.isoformat()]),
        {"week_start": week.isoformat()},
    )
    assert not MealPlanEntry.objects.filter(user=user, date=monday).exists()

    client.post(
        reverse("easy_kitchen:planner-assign"),
        {"week_start": week.isoformat(), "date": monday.isoformat(), "recipe": soup.pk},
    )
    response = client.post(
        reverse("easy_kitchen:planner-add-to-list"),
        {"week_start": week.isoformat(), "title": "Plan shop"},
    )
    shopping_list = ShoppingList.objects.get(user=user, title="Plan shop")
    assert response.status_code == 302
    assert response["Location"] == reverse("easy_kitchen:detail", args=[shopping_list.pk])

    onion = shopping_list.items.get(name="Onion")
    assert onion.quantity == "3"


@pytest.mark.django_db
def test_planner_entries_are_private(client, user, other_user):
    week = week_start_for(date(2026, 11, 3))
    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Onion"}])
    client.force_login(user)
    client.post(
        reverse("easy_kitchen:planner-assign"),
        {"week_start": week.isoformat(), "date": week.isoformat(), "recipe": recipe.pk},
    )

    client.force_login(other_user)
    assert MealPlanEntry.objects.filter(user=other_user).count() == 0
    assert client.get(reverse("easy_kitchen:planner")).status_code == 200


@pytest.mark.django_db
def test_planner_fields_have_unique_ids_and_only_offer_owned_recipes(client, user, other_user):
    from html.parser import HTMLParser

    class FormParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.ids = []

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if "id" in attrs:
                self.ids.append(attrs["id"])

    create_recipe(user, title="My soup")
    create_recipe(other_user, title="Private soup")
    client.force_login(user)
    content = client.get(reverse("easy_kitchen:planner")).content.decode()
    parser = FormParser()
    parser.feed(content)

    assert len(parser.ids) == len(set(parser.ids))
    assert "My soup" in content
    assert "Private soup" not in content


@pytest.mark.django_db
@pytest.mark.parametrize("delete_recipe", [False, True])
def test_planner_only_shows_recipe_selection_for_empty_days(client, user, delete_recipe):
    week = date(2026, 11, 2)
    recipe = create_recipe(user, title="Soup")
    set_meal_plan_recipe(user, week, recipe)
    client.force_login(user)
    url = reverse("easy_kitchen:planner")
    selection_id = f'id="plan-{week.isoformat()}_recipe"'
    search_id = f'id="plan-{week.isoformat()}_recipe-search"'

    content = client.get(url, {"week": week.isoformat()}).content.decode()

    assert selection_id not in content
    assert search_id not in content
    assert content.count('name="recipe"') == 6
    assert f'href="{reverse("easy_kitchen:recipe-detail", args=[recipe.pk])}">Soup</a>' in content

    if delete_recipe:
        recipe.delete()
    else:
        client.post(
            reverse("easy_kitchen:planner-clear", args=[week.isoformat()]),
            {"week_start": week.isoformat()},
        )
    content = client.get(url, {"week": week.isoformat()}).content.decode()

    assert selection_id in content
    assert search_id in content
    assert content.count('name="recipe"') == 7


@pytest.mark.django_db
def test_assigning_another_recipe_replaces_the_day_and_rejects_foreign_ids(client, user, other_user):
    day = date(2026, 11, 2)
    soup = create_recipe(user, title="Soup")
    salad = create_recipe(user, title="Salad")
    private = create_recipe(other_user, title="Private")
    client.force_login(user)
    url = reverse("easy_kitchen:planner-assign")
    data = {"date": day.isoformat(), "week_start": day.isoformat()}

    for recipe in (soup, salad, private):
        client.post(url, {**data, "recipe": recipe.pk})

    assert MealPlanEntry.objects.filter(user=user, date=day).count() == 1
    assert MealPlanEntry.objects.get(user=user, date=day).recipe == salad
    assert not MealPlanEntry.objects.filter(user=other_user).exists()
    with pytest.raises(ValueError, match="Recipe not found"):
        set_meal_plan_recipe(user, day, private)


@pytest.mark.django_db
def test_clearing_a_day_only_changes_the_current_users_plan(client, user, other_user):
    day = date(2026, 11, 2)
    recipe = create_recipe(user, title="Soup")
    private = create_recipe(other_user, title="Salad")
    set_meal_plan_recipe(user, day, recipe)
    set_meal_plan_recipe(other_user, day, private)
    client.force_login(user)

    client.post(reverse("easy_kitchen:planner-clear", args=[day.isoformat()]))

    assert not MealPlanEntry.objects.filter(user=user).exists()
    assert MealPlanEntry.objects.filter(user=other_user, date=day, recipe=private).exists()


@pytest.mark.django_db
def test_repeated_recipes_count_each_day_and_only_the_selected_week(user, other_user):
    week = date(2026, 12, 28)
    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Onion", "quantity": "2"}])
    private = create_recipe(other_user, title="Private", ingredients=[{"name": "Secret"}])
    for offset in (0, 6, 7):
        set_meal_plan_recipe(user, week + timedelta(days=offset), recipe)
    set_meal_plan_recipe(other_user, week, private)
    target = ShoppingList.objects.create(user=user, title="Existing")
    create_item(target, name="onion", quantity="1", checked=True)

    result = add_meal_plan_week_to_list(user, week, shopping_list=target)

    assert result == target
    item = target.items.get()
    assert item.quantity == "5"
    assert not item.checked


@pytest.mark.django_db
def test_empty_week_does_not_create_an_empty_shopping_list(client, user):
    client.force_login(user)
    response = client.post(
        reverse("easy_kitchen:planner-add-to-list"),
        {"week_start": "2026-11-02", "title": "Empty week"},
    )

    assert response.status_code == 422
    assert "This week has no planned recipes yet." in response.content.decode()
    assert not ShoppingList.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_week_to_list_rejects_other_users_shopping_lists(client, user, other_user):
    week = date(2026, 11, 2)
    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Onion"}])
    set_meal_plan_recipe(user, week, recipe)
    target = ShoppingList.objects.create(user=other_user, title="Private")
    client.force_login(user)

    response = client.post(
        reverse("easy_kitchen:planner-add-to-list"),
        {"week_start": week.isoformat(), "shopping_list": target.pk},
    )

    assert response.status_code == 422
    assert not target.items.exists()
    with pytest.raises(ValueError, match="Invalid shopping list"):
        add_meal_plan_week_to_list(user, week, shopping_list=target)


@pytest.mark.django_db
def test_building_a_weekly_list_is_atomic(user):
    week = date(2026, 11, 2)
    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Onion"}, {"name": "Stock"}])
    set_meal_plan_recipe(user, week, recipe)
    from easy_kitchen import services

    original_create_item = services.create_item

    def fail_on_second_item(shopping_list, **kwargs):
        if kwargs["name"] == "Stock":
            raise IntegrityError("Ingredient could not be added")
        return original_create_item(shopping_list, **kwargs)

    with patch.object(services, "create_item", side_effect=fail_on_second_item):
        with pytest.raises(IntegrityError):
            add_meal_plan_week_to_list(user, week, shopping_list=None, title="Weekly shop")

    assert not ShoppingList.objects.filter(user=user).exists()
    assert not user.articles.exists()


@pytest.mark.django_db
def test_week_navigation_normalizes_to_monday_and_preserves_year_boundary(client, user):
    client.force_login(user)
    response = client.get(reverse("easy_kitchen:planner"), {"week": "2027-01-01"})

    assert response.context["week_start"] == date(2026, 12, 28)
    assert response.context["week_end"] == date(2027, 1, 3)
    assert response.context["prev_week"] == date(2026, 12, 21)
    assert response.context["next_week"] == date(2027, 1, 4)


@pytest.mark.django_db
@pytest.mark.parametrize("action", ["planner", "planner-assign", "planner-clear", "planner-add-to-list"])
def test_planner_requires_login(client, action):
    url = reverse(f"easy_kitchen:{action}", args=["2026-11-02"] if action == "planner-clear" else [])
    response = client.get(url) if action == "planner" else client.post(url)

    assert response.status_code == 302
    assert response["Location"].startswith(reverse("login"))


@pytest.mark.django_db
def test_planner_uses_german_translations(client, user):
    client.force_login(user)
    with translation.override("de"):
        content = client.get(reverse("easy_kitchen:planner")).content.decode()

    assert "Wochenplaner" in content
    assert "Rezept suchen" in content
    assert "Kein Rezept geplant" not in content
    assert "Suche in Titeln, Beschreibungen, Zutaten und Zubereitungsschritten." in content
    assert "Einkaufsliste aus Plan erstellen" in content


@pytest.mark.django_db
def test_planner_search_data_includes_owned_recipe_text_and_escapes_html(client, user, other_user):
    recipe = create_recipe(
        user,
        title="Soup",
        description='Fresh </script><script>alert("recipe")</script>',
        ingredients=[{"name": "Onion", "quantity": "200 g"}],
        steps=[{"text": "Simmer slowly."}],
    )
    create_recipe(
        other_user,
        title="Private recipe",
        description="Private description",
        ingredients=[{"name": "Private ingredient"}],
        steps=[{"text": "Private instructions"}],
    )
    client.force_login(user)

    content = client.get(reverse("easy_kitchen:planner")).content.decode()

    data = re.search(
        r'<script id="recipe-search-data" type="application/json">(.*?)</script>', content, re.S
    )
    assert data is not None
    assert "</script>" not in data.group(1)
    documents = json.loads(data.group(1))
    assert set(documents) == {str(recipe.pk)}
    text = documents[str(recipe.pk)]
    for term in ("Soup", recipe.description, "Onion", "200 g", "Simmer slowly."):
        assert term in text
    for term in ("Private recipe", "Private description", "Private ingredient", "Private instructions"):
        assert term not in content
