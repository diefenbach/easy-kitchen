from datetime import date, timedelta

import pytest
from django.urls import reverse

from easy_kitchen.models import MealPlanEntry, ShoppingList
from easy_kitchen.services import create_recipe, week_start_for


@pytest.mark.django_db
def test_planner_week_view_lists_seven_days(client, user):
    client.force_login(user)
    week = week_start_for(date(2026, 11, 3))  # Monday

    content = client.get(reverse("easy_kitchen:planner"), {"week": week.isoformat()}).content.decode()

    assert "Meal planner" in content
    assert "Create shopping list from plan" in content
    assert content.count("No recipe planned") == 7


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
