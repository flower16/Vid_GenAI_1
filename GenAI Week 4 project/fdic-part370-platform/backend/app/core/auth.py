"""
Azure AD SSO + RBAC.

Validates a bearer JWT issued by Azure AD (OIDC) and enforces role-based access.
In `local` environment, auth is bypassed with a synthetic admin principal so the
platform is runnable without a tenant. Wire `azure_*` settings for production.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import Depends, Header, HTTPException, status

from .config import settings


@dataclass
class Principal:
    sub: str
    name: str
    roles: list[str] = field(default_factory=list)


# RBAC matrix: required role per capability
ROLE_REQUIREMENTS = {
    "run_determination": {"Analyst", "Reviewer", "Admin"},
    "view_audit": {"Reviewer", "Admin"},
    "seed_rag": {"Admin"},
}


async def get_principal(authorization: str | None = Header(default=None)) -> Principal:
    if settings.environment == "local":
        return Principal(sub="local-dev", name="Local Dev", roles=["Admin"])
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.split(" ", 1)[1]
    return _validate_azure_jwt(token)


def _validate_azure_jwt(token: str) -> Principal:  # pragma: no cover - external
    """Validate Azure AD JWT signature, issuer, audience; extract roles."""
    import jwt
    from jwt import PyJWKClient

    issuer = f"https://login.microsoftonline.com/{settings.azure_tenant_id}/v2.0"
    jwks = PyJWKClient(
        f"https://login.microsoftonline.com/{settings.azure_tenant_id}/discovery/v2.0/keys"
    )
    signing_key = jwks.get_signing_key_from_jwt(token).key
    claims = jwt.decode(token, signing_key, algorithms=["RS256"],
                        audience=settings.azure_audience or settings.azure_client_id,
                        issuer=issuer)
    return Principal(sub=claims["sub"], name=claims.get("name", ""),
                     roles=claims.get("roles", []))


def require(capability: str):
    """Dependency factory enforcing RBAC for a capability."""
    async def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        allowed = ROLE_REQUIREMENTS.get(capability, set())
        if allowed and not (set(principal.roles) & allowed):
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                f"Requires one of roles: {sorted(allowed)}")
        return principal
    return _dep
