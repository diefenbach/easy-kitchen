"""signed_in_user: the typed way to get the user of a request that is behind a login."""

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory

from easy_kitchen.authentication import signed_in_user


@pytest.mark.django_db
def test_returns_the_signed_in_user(user):
    request = RequestFactory().get("/")
    request.user = user

    assert signed_in_user(request) is user


def test_refuses_an_anonymous_request():
    request = RequestFactory().get("/")
    request.user = AnonymousUser()

    with pytest.raises(PermissionDenied):
        signed_in_user(request)
