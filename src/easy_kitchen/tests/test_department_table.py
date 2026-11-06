import pytest
from django.db import models

from easy_kitchen.models import Article, ShoppingItem

pytestmark = pytest.mark.django_db


def test_articles_and_items_reference_a_department_table():
    from easy_kitchen.models import Department

    assert Department.objects.count() == 21
    assert isinstance(Department._meta.pk, models.BigAutoField)
    for model in (Article, ShoppingItem):
        field = model._meta.get_field("department")
        assert isinstance(field, models.ForeignKey)
        assert field.related_model is Department
        assert field.null


def test_database_departments_are_used_by_forms_services_and_grouping(user, shopping_list):
    from easy_kitchen.models import Department
    from easy_kitchen.forms import ShoppingItemForm
    from easy_kitchen.services import create_item
    from easy_kitchen.templatetags.departments import department_groups

    department = Department.objects.create(code="garden", name="Garden", position=22)
    form = ShoppingItemForm({"name": "Seeds", "department": "garden"})
    assert form.is_valid(), form.errors
    assert form.cleaned_data["department"] == department
    item = create_item(shopping_list, name="Seeds", department="garden")
    assert item.department_id == department.pk
    assert user.articles.get(name="Seeds").department_id == department.pk
    assert department_groups(shopping_list)[0]["value"] == "garden"


def test_deleting_department_keeps_articles_and_items_unassigned(user, shopping_list):
    from easy_kitchen.models import Department
    from easy_kitchen.services import create_item

    item = create_item(shopping_list, name="Milk", department="dairy")
    article = user.articles.get(name="Milk")
    Department.objects.get(code="dairy").delete()
    item.refresh_from_db()
    article.refresh_from_db()
    assert item.department_id is None
    assert article.department_id is None
