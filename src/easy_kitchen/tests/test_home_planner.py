from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import translation

from easy_kitchen.models import MealPlanEntry, Recipe


@pytest.mark.django_db
def test_home_shows_only_current_users_current_week_in_date_order(client, user, other_user):
    client.force_login(user)
    monday = date(2026, 12, 28)
    own_recipe = Recipe.objects.create(user=user, title="Weekly pasta", image_url="https://example.com/pasta.jpg")
    foreign_recipe = Recipe.objects.create(user=other_user, title="Private dinner")
    for offset in (6, 0, -1, 7):
        MealPlanEntry.objects.create(user=user, date=monday + timedelta(days=offset), recipe=own_recipe)
    MealPlanEntry.objects.create(user=other_user, date=monday, recipe=foreign_recipe)

    with patch("easy_kitchen.views.timezone.localdate", return_value=date(2027, 1, 1)):
        response = client.get(reverse("easy_kitchen:home"))

    assert response.status_code == 200
    entries = response.context["planned_meals"]
    assert [entry.date for entry in entries] == [monday, monday + timedelta(days=6)]
    assert response.context["week_start"] == monday
    assert response.context["week_end"] == date(2027, 1, 3)
    section = response.content.decode().split('id="home-meal-plan"')[1].split("</section>")[0]
    assert section.count("Weekly pasta") == 2
    assert "Private dinner" not in section
    assert f'href="{reverse("easy_kitchen:recipe-detail", args=[own_recipe.pk])}"' in section
    assert "https://example.com/pasta.jpg" in section
    assert reverse("easy_kitchen:planner") in section


@pytest.mark.django_db
def test_home_empty_week_is_translated(client, user):
    client.force_login(user)
    with translation.override("de"):
        response = client.get(reverse("easy_kitchen:home"))
    assert response.context["planned_meals"] == []
    assert response.context["next_week_planned_meals"] == []
    content = response.content.decode()
    assert "Geplante Gerichte nächster Woche" in content
    assert "Für nächste Woche sind noch keine Gerichte geplant." in content
    assert "Geplante Gerichte dieser Woche" in content
    assert "Für diese Woche sind noch keine Gerichte geplant." in content


@pytest.mark.django_db
def test_home_shows_next_week_in_date_order_and_scoped_to_user(client, user, other_user):
    client.force_login(user)
    monday = date(2026, 12, 28)
    recipe = Recipe.objects.create(user=user, title="Next week pasta")
    private_recipe = Recipe.objects.create(user=other_user, title="Private next week")
    for offset in (14, 13, 7, 6):
        MealPlanEntry.objects.create(user=user, date=monday + timedelta(days=offset), recipe=recipe)
    MealPlanEntry.objects.create(user=other_user, date=monday + timedelta(days=8), recipe=private_recipe)

    with patch("easy_kitchen.views.timezone.localdate", return_value=date(2027, 1, 3)):
        response = client.get(reverse("easy_kitchen:home"))

    assert response.context["next_week_start"] == date(2027, 1, 4)
    assert response.context["next_week_end"] == date(2027, 1, 10)
    assert [entry.date for entry in response.context["next_week_planned_meals"]] == [
        date(2027, 1, 4), date(2027, 1, 10)
    ]
    section = response.content.decode().split('id="home-next-week-meal-plan"')[1].split("</section>")[0]
    assert "Planned meals next week" in section
    assert section.count("Next week pasta") == 2
    assert "Private next week" not in section
    assert f'href="{reverse("easy_kitchen:recipe-detail", args=[recipe.pk])}"' in section
    assert f'href="{reverse("easy_kitchen:planner")}?week=2027-01-04"' in section
