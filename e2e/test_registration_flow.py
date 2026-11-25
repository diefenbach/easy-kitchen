"""Browser test of sign-up, email confirmation, and sign-in."""

import re

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


def test_signup_confirm_email_and_sign_in(page, live_server, mailoutbox):
    page.goto(f"{live_server.url}/accounts/login/")
    page.get_by_role("link", name="Create an account").click()

    page.get_by_label("Email").fill("new-cook@example.com")
    page.get_by_label("Password", exact=True).fill("Sup3r-secret-pass")
    page.get_by_label("Password (again)").fill("Sup3r-secret-pass")
    page.get_by_role("button", name="Create account").click()
    expect(page.get_by_role("heading", name="Verify Your Email Address")).to_be_visible()

    link = re.search(r"https?://\S+/accounts/confirm-email/\S+/", mailoutbox[0].body).group(0)
    page.goto(link)
    page.get_by_role("button", name="Confirm").click()

    expect(page.get_by_role("heading", name="Shopping lists")).to_be_visible()
    page.get_by_role("button", name="new-cook@example.com", exact=True).click()
    page.get_by_role("button", name="Log out", exact=True).click()

    page.get_by_label("Email").fill("new-cook@example.com")
    page.get_by_label("Password").fill("Sup3r-secret-pass")
    page.get_by_role("button", name="Sign in", exact=True).click()
    expect(page.get_by_role("heading", name="Shopping lists")).to_be_visible()
