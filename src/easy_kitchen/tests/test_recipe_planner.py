from datetime import date

import pytest
from django.urls import reverse
from django.utils import translation

from easy_kitchen.models import MealPlanEntry
from easy_kitchen.services import create_recipe, set_meal_plan_recipe


@pytest.mark.django_db
def test_recipe_can_be_planned_from_its_detail_page(client, user):
    recipe = create_recipe(user, title="Soup")
    client.force_login(user)
    response = client.post(
        reverse("easy_kitchen:recipe-add-to-planner", args=[recipe.pk]),
        {"date": "2027-01-06"},
        follow=True,
    )
    assert response.status_code == 200
    assert response.redirect_chain == [(reverse("easy_kitchen:planner") + "?week=2027-01-04", 302)]
    assert MealPlanEntry.objects.get(user=user, date=date(2027, 1, 6)).recipe == recipe
    assert not list(response.context["messages"])


@pytest.mark.django_db
@pytest.mark.parametrize("day", ["", "not-a-date", "2027-02-30"])
def test_invalid_date_keeps_recipe_page_and_reopens_the_modal(client, user, day):
    recipe = create_recipe(user, title="Soup")
    client.force_login(user)
    response = client.post(
        reverse("easy_kitchen:recipe-add-to-planner", args=[recipe.pk]), {"date": day}
    )
    assert response.status_code == 422
    assert response.context["recipe"] == recipe
    assert response.context["add_to_planner_form"].errors["date"]
    assert 'data-open-on-error="true"' in response.content.decode()
    assert not MealPlanEntry.objects.exists()


@pytest.mark.django_db
def test_recipe_planning_is_private_and_replaces_only_the_users_day(client, user, other_user):
    day = date(2027, 1, 6)
    original = create_recipe(user, title="Soup")
    replacement = create_recipe(user, title="Salad")
    private = create_recipe(other_user, title="Private")
    set_meal_plan_recipe(user, day, original)
    set_meal_plan_recipe(other_user, day, private)
    client.force_login(user)

    response = client.post(
        reverse("easy_kitchen:recipe-add-to-planner", args=[replacement.pk]), {"date": str(day)}
    )
    assert response.status_code == 302
    assert MealPlanEntry.objects.get(user=user, date=day).recipe == replacement
    assert MealPlanEntry.objects.get(user=other_user, date=day).recipe == private
    assert client.post(
        reverse("easy_kitchen:recipe-add-to-planner", args=[private.pk]), {"date": "2027-01-07"}
    ).status_code == 404
    assert MealPlanEntry.objects.count() == 2


@pytest.mark.django_db
def test_recipe_planning_requires_login_and_post(client, user):
    recipe = create_recipe(user, title="Soup")
    url = reverse("easy_kitchen:recipe-add-to-planner", args=[recipe.pk])
    assert client.post(url, {"date": "2027-01-06"}).status_code == 302
    client.force_login(user)
    assert client.get(url).status_code == 405
    assert not MealPlanEntry.objects.exists()


@pytest.mark.django_db
def test_recipe_planning_modal_uses_a_native_datepicker_and_german_labels(client, user):
    recipe = create_recipe(user, title="Soup")
    client.force_login(user)
    with translation.override("de"):
        response = client.get(reverse("easy_kitchen:recipe-detail", args=[recipe.pk]))
    content = response.content.decode()
    assert 'type="date"' in content
    assert "Rezept planen" in content
    assert "Auf Einkaufsliste setzen" in content
    assert "Auf eine Einkaufsliste setzen" not in content
    assert "Zum Wochenplaner hinzufügen" in content
    assert "Datum" in content
    assert response.context["add_to_planner_form"].fields["date"].required


@pytest.mark.django_db
def test_recipe_overview_has_owned_actions_and_only_one_modal_per_action(client, user, other_user):
    recipe = create_recipe(user, title="Soup")
    private = create_recipe(other_user, title="Private recipe")
    other_user.shopping_lists.create(title="Private shopping list")
    client.force_login(user)
    content = client.get(reverse("easy_kitchen:recipes")).content.decode()
    for action in ("recipe-add-to-planner", "recipe-add-to-list"):
        assert reverse(f"easy_kitchen:{action}", args=[recipe.pk]) in content
        assert reverse(f"easy_kitchen:{action}", args=[private.pk]) not in content
    assert content.count('id="add-to-list-modal"') == 1
    assert content.count('id="add-to-planner-modal"') == 1
    assert "Private recipe" not in content
    assert "Private shopping list" not in content
