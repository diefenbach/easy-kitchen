from datetime import date

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from easy_kitchen.models import MealPlanEntry, ShoppingList
from easy_kitchen.services import create_recipe, set_meal_plan_recipe, week_start_for

pytestmark = pytest.mark.django_db


@pytest.fixture
def api(user):
    client = APIClient()
    token = Token.objects.create(user=user)
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


def day_url(day="2027-01-01"):
    return reverse("meal-plan-detail", kwargs={"date": day})


def test_week_has_seven_days_and_only_the_token_owners_recipes(api, user, other_user):
    soup = create_recipe(user, title="Soup")
    private = create_recipe(other_user, title="Private")
    set_meal_plan_recipe(user, date(2027, 1, 1), soup)
    set_meal_plan_recipe(other_user, date(2026, 12, 28), private)
    set_meal_plan_recipe(user, date(2027, 1, 4), soup)
    response = api.get(reverse("meal-plan-list"), {"week": "2027-01-01"})
    assert response.status_code == 200
    data = response.json()
    assert data["week_start"] == "2026-12-28"
    assert data["week_end"] == "2027-01-03"
    assert len(data["days"]) == 7
    assert data["days"][0] == {"date": "2026-12-28", "recipe": None}
    assert data["days"][4] == {"date": "2027-01-01", "recipe": {"id": soup.pk, "title": "Soup"}}
    assert sum(day["recipe"] is not None for day in data["days"]) == 1
    assert "Private" not in response.content.decode()


def test_week_defaults_to_the_current_local_week(api):
    response = api.get(reverse("meal-plan-list"))
    assert response.status_code == 200
    assert response.json()["week_start"] == week_start_for(timezone.localdate()).isoformat()


def test_assign_replace_and_clear_are_idempotent_and_private(api, user, other_user):
    soup = create_recipe(user, title="Soup")
    salad = create_recipe(user, title="Salad")
    private = create_recipe(other_user, title="Private")
    set_meal_plan_recipe(other_user, date(2027, 1, 1), private)
    for recipe in (soup, soup, salad):
        response = api.put(day_url(), {"recipe_id": recipe.pk}, format="json")
        assert response.status_code == 200
        assert response.json()["recipe"] == {"id": recipe.pk, "title": recipe.title}
    assert MealPlanEntry.objects.filter(user=user).count() == 1
    assert api.put(day_url(), {"recipe_id": private.pk}, format="json").status_code == 400
    assert MealPlanEntry.objects.get(user=user).recipe == salad
    for _ in range(2):
        assert api.delete(day_url()).status_code == 204
    assert not MealPlanEntry.objects.filter(user=user).exists()
    assert MealPlanEntry.objects.get(user=other_user).recipe == private


@pytest.mark.parametrize("week", ["wrong", "2027-02-30", "9999-12-31"])
def test_invalid_weeks_are_rejected(api, week):
    assert api.get(reverse("meal-plan-list"), {"week": week}).status_code == 400
    response = api.post(reverse("meal-plan-add-to-list"), {"week": week, "title": "Shop"}, format="json")
    assert response.status_code == 400
    assert not ShoppingList.objects.exists()


@pytest.mark.parametrize("data", [{}, {"recipe_id": 0}, {"recipe_id": "x"}, {"recipe_id": None}])
def test_invalid_recipe_selection_does_not_change_the_plan(api, data):
    assert api.put(day_url(), data, format="json").status_code == 400
    assert not MealPlanEntry.objects.exists()


def test_invalid_day_is_rejected(api, user):
    recipe = create_recipe(user, title="Soup")
    assert api.put(day_url("2027-02-30"), {"recipe_id": recipe.pk}, format="json").status_code == 400
    assert api.delete(day_url("2027-02-30")).status_code == 400
    assert not MealPlanEntry.objects.exists()


@pytest.mark.parametrize("existing", [False, True])
def test_copying_a_week_merges_quantities_and_counts_repeated_days(api, user, other_user, existing):
    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Onion", "quantity": "2"}])
    private = create_recipe(other_user, title="Private", ingredients=[{"name": "Secret"}])
    for day in (date(2026, 12, 28), date(2027, 1, 3), date(2027, 1, 4)):
        set_meal_plan_recipe(user, day, recipe)
    set_meal_plan_recipe(other_user, date(2027, 1, 1), private)
    data = {"week": "2027-01-01"}
    if existing:
        target = ShoppingList.objects.create(user=user, title="Shop")
        target.items.create(name="onion", quantity="1", checked=True)
        data["shopping_list_id"] = target.pk
    else:
        data["title"] = "Shop"
    response = api.post(reverse("meal-plan-add-to-list"), data, format="json")
    assert response.status_code == 200
    target = ShoppingList.objects.get(pk=response.json()["id"], user=user)
    item = target.items.get()
    assert item.quantity == ("5" if existing else "4")
    assert not item.checked
    assert MealPlanEntry.objects.filter(user=user).count() == 3
    if existing:
        repeated = api.post(reverse("meal-plan-add-to-list"), data, format="json")
        assert repeated.status_code == 200
        assert target.items.get().quantity == "9"


def test_copying_rejects_empty_weeks_foreign_lists_and_ambiguous_targets(api, user, other_user):
    url = reverse("meal-plan-add-to-list")
    assert api.post(url, {"week": "2027-01-01", "title": "Empty"}, format="json").status_code == 400
    assert not ShoppingList.objects.filter(user=user).exists()
    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Onion"}])
    set_meal_plan_recipe(user, date(2027, 1, 1), recipe)
    private = ShoppingList.objects.create(user=other_user, title="Private")
    own = ShoppingList.objects.create(user=user, title="Own")
    for target in ({}, {"shopping_list_id": private.pk}, {"shopping_list_id": own.pk, "title": "New"}):
        assert api.post(url, {"week": "2027-01-01", **target}, format="json").status_code == 400
    assert not private.items.exists()
    assert not own.items.exists()
    assert not ShoppingList.objects.filter(user=user, title="New").exists()


def test_all_planner_operations_require_authentication(client):
    assert client.get(reverse("meal-plan-list")).status_code == 401
    assert client.put(day_url(), {}, content_type="application/json").status_code == 401
    assert client.delete(day_url()).status_code == 401
    assert client.post(reverse("meal-plan-add-to-list"), {}, content_type="application/json").status_code == 401


def test_schema_documents_planner_operations_and_token_authentication(client):
    response = client.get(reverse("api-schema"), HTTP_ACCEPT="application/vnd.oai.openapi+json")
    assert response.status_code == 200
    schema = response.json()
    paths = schema["paths"]
    assert "get" in paths["/api/v1/meal-planner/"]
    assert "put" in paths["/api/v1/meal-planner/{date}/"]
    assert "delete" in paths["/api/v1/meal-planner/{date}/"]
    assert "post" in paths["/api/v1/meal-planner/add-to-list/"]
    assert paths["/api/v1/meal-planner/"]["get"]["security"]
