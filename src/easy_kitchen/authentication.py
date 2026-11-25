"""Authentication helpers: Bearer tokens for API and MCP, and the typed user of a signed-in request."""

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.plumbing import build_bearer_security_scheme_object
from rest_framework.authentication import TokenAuthentication
from rest_framework.request import Request

from accounts.models import User


class BearerTokenAuthentication(TokenAuthentication):
    """The DRF token sent as the standard `Authorization: Bearer <token>` (RFC 6750)."""

    keyword = "Bearer"


class BearerTokenScheme(OpenApiAuthenticationExtension):
    """Document BearerTokenAuthentication as HTTP bearer instead of drf-spectacular's `Token` API key."""

    target_class = BearerTokenAuthentication
    name = "bearerAuth"
    priority = 1

    def get_security_definition(self, auto_schema):
        return build_bearer_security_scheme_object(header_name="AUTHORIZATION", token_prefix="Bearer")


def signed_in_user(request: HttpRequest | Request) -> User:
    """Return the EasyKitchen user of a request behind a login, or refuse it with 403.

    Django types `request.user` as any user or `AnonymousUser`; views behind `LoginRequiredMixin` or DRF's
    `IsAuthenticated` always have a `User`. This narrows the type and fails loudly if that ever stops being true.
    """
    user = request.user
    if not isinstance(user, User):
        raise PermissionDenied
    return user
