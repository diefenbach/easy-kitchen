from unittest.mock import patch

import pytest
from django.urls import reverse

from easy_kitchen.models import Department
from easy_kitchen.services import create_item

pytestmark = pytest.mark.django_db


def editor_data(user, **overrides):
    departments = list(user.departments.order_by("name", "id"))
    data = {"departments-TOTAL_FORMS": str(len(departments)), "departments-INITIAL_FORMS": str(len(departments))}
    for index, department in enumerate(departments):
        data.update({f"departments-{index}-id": str(department.pk), f"departments-{index}-name": department.name})
    return data | overrides


def test_department_editor_requires_login_and_is_in_the_user_menu(client, user):
    url = reverse("easy_kitchen:departments")
    assert client.get(url).status_code == 302
    client.force_login(user)
    response = client.get(url)
    assert response.status_code == 200
    assert 'department-editor-footer' in response.content.decode()
    assert url in client.get(reverse("easy_kitchen:home")).content.decode()


def test_department_changes_save_together_and_keep_stable_references(client, user, other_user, shopping_list):
    item = create_item(shopping_list, name="Milk", department="dairy")
    dairy = user.departments.get(code="dairy")
    removed = user.departments.get(code="bread")
    own_bread = user.articles.create(name="Bread", department=removed)
    foreign_bread = other_user.departments.get(code="bread")
    other_user.articles.create(name="Toast", department=foreign_bread)
    data = editor_data(user)
    count = int(data["departments-TOTAL_FORMS"])
    for index in range(count):
        if data[f"departments-{index}-id"] == str(dairy.pk):
            data[f"departments-{index}-name"] = "Milk products"
        if data[f"departments-{index}-id"] == str(removed.pk):
            data[f"departments-{index}-DELETE"] = "on"
    data.update({"departments-TOTAL_FORMS": str(count + 1), f"departments-{count}-name": " Garden supplies "})
    client.force_login(user)
    response = client.post(reverse("easy_kitchen:departments"), data)
    assert response.status_code == 302
    dairy.refresh_from_db()
    item.refresh_from_db()
    assert dairy.name == "Milk products" and dairy.code == "dairy"
    assert item.department_id == dairy.pk
    assert not Department.objects.filter(pk=removed.pk).exists()
    own_bread.refresh_from_db()
    assert own_bread.department_id is None
    assert other_user.articles.get(name="Toast").department_id == foreign_bread.pk
    assert user.departments.get(name="Garden supplies").code == "garden-supplies"


@pytest.mark.parametrize("invalid", [
    {"departments-0-name": ""}, {"departments-0-name": " bread "},
    {"departments-0-id": "999999999", "departments-0-DELETE": "on"},
])
def test_invalid_department_drafts_do_not_partially_save(client, user, invalid):
    client.force_login(user)
    before = list(Department.objects.values_list("pk", "name", "code"))
    response = client.post(reverse("easy_kitchen:departments"), editor_data(user, **invalid), HTTP_HX_REQUEST="true")
    assert response.status_code == 422
    assert response["X-Department-Editor"] == "true"
    assert list(Department.objects.values_list("pk", "name", "code")) == before


def test_department_save_is_atomic(client, user, shopping_list):
    item = create_item(shopping_list, name="Milk", department="dairy")
    data = editor_data(user, **{"departments-0-name": "New baby supplies"})
    dairy = user.departments.get(code="dairy")
    for index in range(int(data["departments-TOTAL_FORMS"])):
        if data[f"departments-{index}-id"] == str(dairy.pk):
            data[f"departments-{index}-DELETE"] = "on"
    client.force_login(user)
    with patch.object(Department, "save", side_effect=RuntimeError("Save failed")):
        with pytest.raises(RuntimeError, match="Save failed"):
            client.post(reverse("easy_kitchen:departments"), data)
    item.refresh_from_db()
    assert item.department_id == dairy.pk
    assert user.departments.get(code="baby").name == "Baby"


def test_department_editor_rejects_foreign_ids_including_deleted_rows(client, user, other_user):
    foreign = other_user.departments.get(code="baby")
    client.force_login(user)
    for deleted in (False, True):
        data = editor_data(user, **{"departments-0-id": str(foreign.pk), "departments-0-name": "Changed"})
        if deleted:
            data["departments-0-DELETE"] = "on"
        response = client.post(reverse("easy_kitchen:departments"), data)
        assert response.status_code == 422
    foreign.refresh_from_db()
    assert foreign.name == "Baby"


def test_department_service_rejects_foreign_ids(user, other_user):
    from easy_kitchen.services import save_departments

    foreign = other_user.departments.get(code="baby")
    with pytest.raises(ValueError, match="Invalid department selection"):
        save_departments(user, [{"id": foreign.pk, "name": "Changed"}], [])
    with pytest.raises(ValueError, match="Invalid department selection"):
        save_departments(user, [], [foreign.pk])
    assert other_user.departments.filter(pk=foreign.pk).exists()


def test_german_editor_displays_translations_and_preserves_canonical_names(client, user):
    from django.utils.translation import override

    client.force_login(user)
    with override("de"):
        response = client.get(reverse("easy_kitchen:departments"))
        formset = response.context["department_formset"]
        data = editor_data(user)
        for index, form in enumerate(formset):
            data[f"departments-{index}-name"] = form["name"].value()
        assert "Milchprodukte" in data.values()
        assert client.post(reverse("easy_kitchen:departments"), data).status_code == 302
    assert user.departments.get(code="dairy").name == "Dairy products"
