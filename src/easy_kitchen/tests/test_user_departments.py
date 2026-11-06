import pytest
from django.contrib.auth import get_user_model

from easy_kitchen.models import Department
from easy_kitchen.services import create_item

pytestmark = pytest.mark.django_db


def test_new_users_receive_independent_default_departments(user, other_user):
    assert user.departments.count() == other_user.departments.count() == 21
    assert set(user.departments.values_list("code", flat=True)) == set(other_user.departments.values_list("code", flat=True))
    assert not set(user.departments.values_list("pk", flat=True)) & set(other_user.departments.values_list("pk", flat=True))
    own = user.departments.get(code="dairy")
    own.name = "My dairy"
    own.save()
    user.save()
    assert user.departments.count() == 21
    assert other_user.departments.get(code="dairy").name == "Dairy products"


def test_services_reject_another_users_department_even_with_the_same_code(shopping_list, other_user):
    foreign = other_user.departments.get(code="dairy")
    with pytest.raises(ValueError, match="Invalid department"):
        create_item(shopping_list, name="Milk", department=foreign)
    assert not shopping_list.items.exists()
    assert not shopping_list.user.articles.exists()


def test_deleted_defaults_are_not_recreated_on_user_update(user):
    user.departments.get(code="dairy").delete()
    user.save()
    assert user.departments.count() == 20
    assert not user.departments.filter(code="dairy").exists()


def test_duplicate_codes_are_allowed_only_for_different_users(user, other_user):
    from django.db import IntegrityError, transaction

    assert Department.objects.filter(code="dairy").count() == 2
    with pytest.raises(IntegrityError), transaction.atomic():
        Department.objects.create(user=user, code="dairy", name="Duplicate")


def test_creating_user_through_the_standard_manager_seeds_defaults():
    user = get_user_model().objects.create_user(username="new-user", password="test-password")
    assert user.departments.count() == 21


def test_foreign_department_is_not_visible_or_accepted_in_forms(client, user, other_user, shopping_list):
    from django.urls import reverse
    from easy_kitchen.forms import ShoppingItemForm, ArticleForm
    from easy_kitchen.api.serializers import ShoppingListSerializer

    foreign = other_user.departments.create(code="private", name="Private department")
    client.force_login(user)
    html = client.get(reverse("easy_kitchen:departments")).content.decode()
    assert foreign.name not in html
    form = ShoppingItemForm({"name": "Secret", "department": "private"}, user=user)
    assert not form.is_valid()
    article = ArticleForm({"name": "Secret", "department": "private"}, user=user)
    assert not article.is_valid()
    serializer = ShoppingListSerializer(data={"title": "Bad", "items": [{"name": "Secret", "department": "private"}]}, context={"user": user})
    assert not serializer.is_valid()
    with pytest.raises(ValueError, match="Invalid department"):
        create_item(shopping_list, name="Secret", department="private")
