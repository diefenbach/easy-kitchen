import pytest
from django.urls import reverse
from mcp.server.mcpserver.exceptions import ToolError
from rest_framework.authtoken.models import Token

from easy_kitchen.mcp_server import user_from_authorization

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("scheme", ["Bearer", "bearer"])
def test_api_accepts_bearer_tokens(client, user, scheme):
    token = Token.objects.create(user=user)

    response = client.get(reverse("shopping-list-list"), HTTP_AUTHORIZATION=f"{scheme} {token.key}")

    assert response.status_code == 200


def test_api_rejects_an_unknown_bearer_token(client, user):
    response = client.get(reverse("shopping-list-list"), HTTP_AUTHORIZATION="Bearer not-a-token")

    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Bearer"


def test_api_rejects_the_old_token_scheme(client, user):
    token = Token.objects.create(user=user)

    response = client.get(reverse("shopping-list-list"), HTTP_AUTHORIZATION=f"Token {token.key}")

    assert response.status_code == 401


@pytest.mark.parametrize("scheme", ["Bearer", "bearer"])
def test_mcp_accepts_bearer_tokens(user, scheme):
    token = Token.objects.create(user=user)

    assert user_from_authorization(f"{scheme} {token.key}") == user


@pytest.mark.parametrize("header", [None, "", "Basic abc", "Bearer ", "Bearer not-a-token"])
def test_mcp_rejects_missing_or_wrong_credentials(header):
    with pytest.raises(ToolError):
        user_from_authorization(header)


def test_mcp_rejects_the_old_token_scheme(user):
    token = Token.objects.create(user=user)

    with pytest.raises(ToolError, match="Bearer"):
        user_from_authorization(f"Token {token.key}")


def test_openapi_schema_documents_bearer_authentication(client, user):
    client.force_login(user)

    schema = client.get(reverse("api-schema"), HTTP_ACCEPT="application/json").json()

    schemes = schema["components"]["securitySchemes"]
    assert {"type": "http", "scheme": "bearer"} in [
        {key: value for key, value in scheme.items() if key in {"type", "scheme"}} for scheme in schemes.values()
    ]
