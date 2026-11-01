import os

import pytest
from django.contrib.auth import get_user_model

# Playwright's sync API owns an event loop while browser tests run. Django's ORM
# stays synchronous in these tests, so permit it only in this pytest process.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="e2e-user", password="test-password")


@pytest.fixture
def other_user(db):
    return get_user_model().objects.create_user(username="e2e-other", password="test-password")


@pytest.fixture
def authenticated_page(page, live_server, user):
    page.goto(f"{live_server.url}/accounts/login/")
    page.get_by_label("Username").fill(user.username)
    page.get_by_label("Password").fill("test-password")
    page.get_by_role("button", name="Sign in").click()
    page.get_by_role("heading", name="Shopping lists").wait_for()
    return page
