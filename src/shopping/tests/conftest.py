import pytest
from django.contrib.auth import get_user_model
from shopping.models import ShoppingList


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="kai", password="test-password")


@pytest.fixture
def other_user(db):
    return get_user_model().objects.create_user(username="other", password="test-password")


@pytest.fixture
def shopping_list(user):
    return ShoppingList.objects.create(user=user, title="Wocheneinkauf")
