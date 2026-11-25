import re
from unittest import mock
from urllib.parse import parse_qs, urlparse

import pytest
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from easy_kitchen.models import Department

GOOGLE_PROVIDERS = {
    "google": {
        "APPS": [{"client_id": "google-client-id", "secret": "google-secret", "key": ""}],
        "SCOPE": ["profile", "email"],
    }
}


def signup(client, email="new@example.com", password="Sup3r-secret-pass"):
    return client.post(
        reverse("account_signup"),
        {"email": email, "password1": password, "password2": password},
    )


def confirmation_link(message):
    return re.search(r"https?://[^/\s]+(/accounts/confirm-email/\S+/)", message.body).group(1)


@pytest.mark.django_db
def test_signup_sends_a_confirmation_email_and_does_not_sign_in(client, mailoutbox):
    response = signup(client)

    assert response.status_code == 302
    assert response.url == reverse("account_email_verification_sent")
    user = get_user_model().objects.get(email="new@example.com")
    assert not EmailAddress.objects.get(user=user).verified
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["new@example.com"]
    assert client.get(reverse("easy_kitchen:home")).status_code == 302


@pytest.mark.django_db
def test_signup_seeds_the_default_departments(client):
    signup(client)

    user = get_user_model().objects.get(email="new@example.com")
    assert Department.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_signup_with_a_taken_email_keeps_one_account_and_does_not_reveal_it(
    client, user, mailoutbox
):
    response = signup(client, email=user.email)

    assert response.status_code == 302
    assert response.url == reverse("account_email_verification_sent")
    assert get_user_model().objects.filter(email__iexact=user.email).count() == 1
    assert mailoutbox[0].to == [user.email]


@pytest.mark.django_db
def test_unverified_user_cannot_sign_in(client, mailoutbox):
    signup(client)
    client.logout()

    response = client.post(
        reverse("account_login"), {"login": "new@example.com", "password": "Sup3r-secret-pass"}
    )

    assert response.status_code == 302
    assert response.url == reverse("account_email_verification_sent")
    assert client.get(reverse("easy_kitchen:home")).status_code == 302


@pytest.mark.django_db
def test_confirmation_link_verifies_the_address_and_signs_in(client, mailoutbox):
    signup(client)
    link = confirmation_link(mailoutbox[0])

    response = client.post(link)

    assert response.status_code == 302
    assert response.url == reverse("easy_kitchen:home")
    assert EmailAddress.objects.get(email="new@example.com").verified
    assert client.get(reverse("easy_kitchen:home")).status_code == 200


@pytest.mark.django_db
def test_login_page_links_to_signup_and_password_reset(client):
    content = client.get(reverse("account_login")).content.decode()

    assert reverse("account_signup") in content
    assert reverse("account_reset_password") in content


@pytest.mark.django_db
def test_password_reset_sends_an_email(client, user, mailoutbox):
    response = client.post(reverse("account_reset_password"), {"email": user.email})

    assert response.status_code == 302
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == [user.email]


@pytest.mark.django_db
@override_settings(SOCIALACCOUNT_PROVIDERS={})
def test_google_button_is_hidden_without_credentials(client):
    content = client.get(reverse("account_login")).content.decode()

    assert "Google" not in content


@pytest.mark.django_db
@override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE_PROVIDERS)
def test_google_button_is_shown_when_configured(client):
    content = client.get(reverse("account_login")).content.decode()

    assert "Google" in content
    assert reverse("google_login") in content


def complete_google_login(client, claims):
    response = client.post(reverse("google_login"))
    assert response.status_code == 302
    state = parse_qs(urlparse(response.url).query)["state"][0]
    with (
        mock.patch(
            "allauth.socialaccount.providers.oauth2.client.OAuth2Client.get_access_token",
            return_value={"access_token": "access-token", "id_token": "id-token"},
        ),
        mock.patch(
            "allauth.socialaccount.providers.google.views._verify_and_decode",
            return_value=claims,
        ),
    ):
        return client.get(reverse("google_callback"), {"code": "code", "state": state})


@pytest.mark.django_db
@override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE_PROVIDERS)
def test_google_login_creates_a_verified_account(client):
    response = complete_google_login(
        client, {"sub": "google-1", "email": "cook@gmail.com", "email_verified": True}
    )

    assert response.status_code == 302
    assert response.url == reverse("easy_kitchen:home")
    user = get_user_model().objects.get(email="cook@gmail.com")
    assert EmailAddress.objects.get(user=user).verified
    assert SocialAccount.objects.filter(user=user, provider="google", uid="google-1").exists()
    assert Department.objects.filter(user=user).exists()


@pytest.mark.django_db
@override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE_PROVIDERS)
def test_google_login_connects_an_existing_account_with_the_same_email(client, user):
    response = complete_google_login(
        client, {"sub": "google-2", "email": user.email, "email_verified": True}
    )

    assert response.status_code == 302
    assert response.url == reverse("easy_kitchen:home")
    assert get_user_model().objects.filter(email__iexact=user.email).count() == 1
    assert SocialAccount.objects.filter(user=user, provider="google").exists()


def test_google_provider_is_configured_from_environment(monkeypatch):
    from project.settings.base import google_provider_from_environment

    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    assert google_provider_from_environment() == {}

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
    provider = google_provider_from_environment()["google"]
    assert provider["APPS"] == [{"client_id": "client-id", "secret": "client-secret", "key": ""}]

