"""Optional service authentication and RBAC helpers."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, cast


class ServiceRole(StrEnum):
    """Service authorization roles."""

    READ = "read"
    WRITE = "write"
    EXPORT = "export"
    ADMIN = "admin"


ROLE_ORDER: dict[ServiceRole, int] = {
    ServiceRole.READ: 1,
    ServiceRole.WRITE: 2,
    ServiceRole.EXPORT: 3,
    ServiceRole.ADMIN: 4,
}


@dataclass(frozen=True, slots=True)
class ServicePrincipal:
    """Authenticated service principal."""

    principal_id: str
    roles: frozenset[ServiceRole]

    def has_role(self, required: ServiceRole) -> bool:
        required_rank = ROLE_ORDER[required]
        return any(ROLE_ORDER[role] >= required_rank for role in self.roles)


class ServiceAuthError(RuntimeError):
    """Raised when service authentication or authorization fails."""


class JwtLibraryUnavailable(ServiceAuthError):
    """Raised when the optional JWT runtime dependency is not installed."""


@dataclass(frozen=True, slots=True)
class StaticTokenAuthenticator:
    """Deterministic token authenticator for local service deployments."""

    tokens: dict[str, ServicePrincipal]

    def authenticate(self, token: str | None) -> ServicePrincipal:
        if token is None or token not in self.tokens:
            raise ServiceAuthError("invalid service token")
        return self.tokens[token]


@dataclass(frozen=True, slots=True)
class JwtAuthenticator:
    """JWT authenticator backed by the optional PyJWT service dependency."""

    verification_key: str | bytes
    algorithms: tuple[str, ...]
    issuer: str | None = None
    audience: str | None = None
    principal_claim: str = "sub"
    roles_claim: str = "roles"

    def authenticate(self, token: str | None) -> ServicePrincipal:
        if token is None:
            raise ServiceAuthError("invalid service JWT")
        jwt_module = _jwt_module()
        try:
            claims = jwt_module.decode(
                token,
                self.verification_key,
                algorithms=list(self.algorithms),
                issuer=self.issuer,
                audience=self.audience,
                options={"verify_aud": self.audience is not None},
            )
        except Exception as exc:
            raise ServiceAuthError("invalid service JWT") from exc
        return _principal_from_claims(
            claims,
            principal_claim=self.principal_claim,
            roles_claim=self.roles_claim,
        )


class JwkClient(Protocol):
    """Subset of PyJWT PyJWKClient used by the service authenticator."""

    def get_signing_key_from_jwt(self, token: str) -> SigningKey:
        """Return an object exposing a verification key."""


class SigningKey(Protocol):
    """Subset of a PyJWT signing key result."""

    key: object


type JwkClientFactory = Callable[[str], JwkClient]


class JwtModule(Protocol):
    """Subset of the PyJWT module used by service authentication."""

    PyJWKClient: JwkClientFactory

    def decode(
        self,
        jwt: str,
        key: object,
        *,
        algorithms: list[str],
        issuer: str | None = None,
        audience: str | None = None,
        options: dict[str, bool] | None = None,
    ) -> object:
        """Decode and verify a JWT."""


@dataclass(frozen=True, slots=True)
class OidcJwtAuthenticator:
    """OIDC/JWKS JWT authenticator backed by the optional PyJWT service dependency."""

    jwks_url: str
    algorithms: tuple[str, ...]
    issuer: str
    audience: str
    principal_claim: str = "sub"
    roles_claim: str = "roles"
    jwk_client_factory: JwkClientFactory | None = None

    def authenticate(self, token: str | None) -> ServicePrincipal:
        if token is None:
            raise ServiceAuthError("invalid service OIDC JWT")
        jwt_module = _jwt_module()
        try:
            client = self._jwk_client(jwt_module)
            signing_key = client.get_signing_key_from_jwt(token)
            claims = jwt_module.decode(
                token,
                signing_key.key,
                algorithms=list(self.algorithms),
                issuer=self.issuer,
                audience=self.audience,
            )
        except Exception as exc:
            raise ServiceAuthError("invalid service OIDC JWT") from exc
        return _principal_from_claims(
            claims,
            principal_claim=self.principal_claim,
            roles_claim=self.roles_claim,
        )

    def _jwk_client(self, jwt_module: JwtModule) -> JwkClient:
        if self.jwk_client_factory is not None:
            return self.jwk_client_factory(self.jwks_url)
        return jwt_module.PyJWKClient(self.jwks_url)


def require_role(principal: ServicePrincipal, role: ServiceRole) -> None:
    """Raise if a principal lacks the required role."""

    if not principal.has_role(role):
        raise ServiceAuthError(f"service role required: {role.value}")


def _jwt_module() -> JwtModule:
    try:
        return cast(JwtModule, importlib.import_module("jwt"))
    except ImportError as exc:
        raise JwtLibraryUnavailable(
            "install actionlineage[service] to use JWT service authentication"
        ) from exc


def _principal_from_claims(
    claims: object,
    *,
    principal_claim: str,
    roles_claim: str,
) -> ServicePrincipal:
    if not isinstance(claims, dict):
        raise ServiceAuthError("invalid service JWT claims")
    principal_id = claims.get(principal_claim)
    if not isinstance(principal_id, str) or not principal_id:
        raise ServiceAuthError("invalid service JWT principal")
    return ServicePrincipal(
        principal_id=principal_id,
        roles=frozenset(_roles_from_claim(claims.get(roles_claim))),
    )


def _roles_from_claim(value: Any) -> tuple[ServiceRole, ...]:
    if isinstance(value, str):
        raw_roles = tuple(part for part in value.split() if part)
    elif isinstance(value, list):
        raw_roles = tuple(role for role in value if isinstance(role, str))
    else:
        raise ServiceAuthError("invalid service JWT roles")
    roles: list[ServiceRole] = []
    for raw_role in raw_roles:
        try:
            roles.append(ServiceRole(raw_role))
        except ValueError as exc:
            raise ServiceAuthError("invalid service JWT roles") from exc
    if not roles:
        raise ServiceAuthError("invalid service JWT roles")
    return tuple(roles)
