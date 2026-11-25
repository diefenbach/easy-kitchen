import os

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core.cache import cache

# Playwright's sync API owns an event loop while browser tests run. Django's ORM
# stays synchronous in these tests, so permit it only in this pytest process.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


@pytest.fixture(autouse=True)
def clear_rate_limits():
    """allauth keeps its rate limits in the cache, which would leak between tests."""
    cache.clear()


def verified_user(username, email, password="test-password"):
    user = get_user_model().objects.create_user(username=username, email=email, password=password)
    EmailAddress.objects.create(user=user, email=email, verified=True, primary=True)
    return user


@pytest.fixture
def user(db):
    return verified_user(username="e2e-user", email="e2e-user@example.com")


@pytest.fixture
def other_user(db):
    return verified_user(username="e2e-other", email="e2e-other@example.com")


@pytest.fixture
def authenticated_page(page, live_server, user):
    page.goto(f"{live_server.url}/accounts/login/")
    page.get_by_label("Email").fill(user.email)
    page.get_by_label("Password").fill("test-password")
    page.get_by_role("button", name="Sign in").click()
    page.get_by_role("heading", name="Shopping lists").wait_for()
    return page
