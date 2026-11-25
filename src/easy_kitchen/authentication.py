from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.plumbing import build_bearer_security_scheme_object
from rest_framework.authentication import TokenAuthentication


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
