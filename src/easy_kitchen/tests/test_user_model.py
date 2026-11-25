import pytest
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_the_project_uses_its_own_email_user_model():
    User = get_user_model()
    assert settings.AUTH_USER_MODEL == "accounts.User"
    assert User.USERNAME_FIELD == "email"
    assert User.REQUIRED_FIELDS == []
    assert "username" not in {field.name for field in User._meta.get_fields()}


def test_users_are_created_and_authenticated_by_email():
    user = get_user_model().objects.create_user("Cook@EXAMPLE.com", "secret-password")

    assert user.email == "Cook@example.com"
    assert user.get_username() == "Cook@example.com"
    assert user.check_password("secret-password")
    assert not user.is_staff
    assert authenticate(email="Cook@example.com", password="secret-password") == user


def test_an_email_is_required():
    with pytest.raises(ValueError, match="email"):
        get_user_model().objects.create_user("", "secret-password")


def test_emails_are_unique_ignoring_case():
    users = get_user_model().objects
    users.create_user("cook@example.com")

    with pytest.raises(IntegrityError):
        users.create_user("COOK@example.com")


def test_superusers_are_staff():
    admin = get_user_model().objects.create_superuser("admin@example.com", "secret-password")

    assert admin.is_staff and admin.is_superuser


def test_new_users_still_receive_default_departments():
    user = get_user_model().objects.create_user("new@example.com")

    assert user.departments.count() == 21


def test_a_superuser_without_a_confirmed_address_gets_a_confirmation_mail_on_first_sign_in(client, mailoutbox):
    get_user_model().objects.create_superuser("admin@example.com", "secret-password")

    response = client.post(reverse("account_login"), {"login": "admin@example.com", "password": "secret-password"})

    assert response.status_code == 302
    assert response["Location"] == reverse("account_email_verification_sent")
    assert [message.to for message in mailoutbox] == [["admin@example.com"]]
