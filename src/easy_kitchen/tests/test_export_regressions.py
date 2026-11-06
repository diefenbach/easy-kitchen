from datetime import date

import pytest
from django.urls import reverse

from easy_kitchen.forms import ExportForm
from easy_kitchen.services import (
    create_recipe, create_shopping_list, export_records,
)


@pytest.mark.django_db
@pytest.mark.parametrize("bad_id", ["not-an-integer", "1.5", "9999999999999999999999999999999", [1], {"id": 1}])
def test_export_rejects_malformed_ids_as_form_errors(user, bad_id):
    form = ExportForm({"lists": [bad_id]}, user=user)
    assert not form.is_valid()
    assert "lists" in form.errors


@pytest.mark.django_db
def test_export_invalid_ids_return_validation_response(client, user):
    client.force_login(user)
    response = client.post(reverse("easy_kitchen:export-json"), {"lists": ["not-an-integer"]})
    assert response.status_code == 200
    assert "lists" in response.context["form"].errors


@pytest.mark.django_db
def test_selected_export_query_count_is_constant(user, other_user, django_assert_num_queries):
    lists = [create_shopping_list(user, title=f"List {i}", date=date.today(), items=[{"name": "Milk"}]) for i in range(4)]
    recipes = [create_recipe(user, title=f"Recipe {i}", ingredients=[{"name": "Milk"}], steps=["Mix"]) for i in range(4)]
    foreign = create_shopping_list(other_user, title="Private", date=date.today())
    form = ExportForm({"lists": [x.pk for x in lists] + [foreign.pk], "recipes": [x.pk for x in recipes]}, user=user)
    with django_assert_num_queries(5):
        assert form.is_valid(), form.errors
        result = export_records(lists=form.cleaned_data["lists"], recipes=form.cleaned_data["recipes"])
    assert len(result["lists"]) == len(result["recipes"]) == 4

