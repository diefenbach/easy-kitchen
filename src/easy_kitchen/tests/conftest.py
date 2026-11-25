"""Shared fixtures: verified users, a shopping list, and a cleared rate-limit cache per test."""

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core.cache import cache
from easy_kitchen.models import ShoppingList


@pytest.fixture(autouse=True)
def clear_rate_limits():
    """allauth keeps its rate limits in the cache, which would leak between tests."""
    cache.clear()


def verified_user(email, password="test-password"):
    user = get_user_model().objects.create_user(email, password)
    EmailAddress.objects.create(user=user, email=email, verified=True, primary=True)
    return user


@pytest.fixture
def user(db):
    return verified_user(email="kai@example.com")


@pytest.fixture
def other_user(db):
    return verified_user(email="other@example.com")


@pytest.fixture
def shopping_list(user):
    return ShoppingList.objects.create(user=user, title="Wocheneinkauf")
