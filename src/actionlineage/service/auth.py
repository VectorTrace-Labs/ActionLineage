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


class ServiceCapability(StrEnum):
    """Explicit service capabilities granted by role bundles or credentials."""

    EVENTS_READ = "events:read"
    EVENTS_WRITE = "events:write"
    JOURNAL_VERIFY = "journal:verify"
    PROJECTIONS_REBUILD = "projections:rebuild"
    DETECTIONS_RUN = "detections:run"
    CASES_READ = "cases:read"
    CASES_EXPORT = "cases:export"
    ADMIN_CONFIGURE = "admin:configure"
    TENANTS_MANAGE = "tenants:manage"


ROLE_CAPABILITIES: dict[ServiceRole, frozenset[ServiceCapability]] = {
    ServiceRole.READ: frozenset(
        {
            ServiceCapability.EVENTS_READ,
            ServiceCapability.JOURNAL_VERIFY,
            ServiceCapability.CASES_READ,
        }
    ),
    ServiceRole.WRITE: frozenset(
        {
            ServiceCapability.EVENTS_WRITE,
            ServiceCapability.JOURNAL_VERIFY,
            ServiceCapability.PROJECTIONS_REBUILD,
        }
    ),
    ServiceRole.EXPORT: frozenset({ServiceCapability.CASES_EXPORT}),
    ServiceRole.ADMIN: frozenset(ServiceCapability),
}


@dataclass(frozen=True, slots=True)
class ServicePrincipal:
    """Authenticated service principal."""

    principal_id: str
    roles: frozenset[ServiceRole]
    capabilities: frozenset[ServiceCapability] = frozenset()

    def has_role(self, required: ServiceRole) -> bool:
        return ROLE_CAPABILITIES[required].issubset(self.effective_capabilities)

    @property
    def effective_capabilities(self) -> frozenset[ServiceCapability]:
        """Return explicit capabilities plus capabilities granted by role bundles."""

        capabilities: set[ServiceCapability] = set(self.capabilities)
        for role in self.roles:
            capabilities.update(ROLE_CAPABILITIES[role])
        return frozenset(capabilities)

    def has_capability(self, required: ServiceCapability) -> bool:
        """Return true when the principal has the exact required capability."""

        return required in self.effective_capabilities


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
    capabilities_claim: str = "capabilities"

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
            capabilities_claim=self.capabilities_claim,
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
    capabilities_claim: str = "capabilities"
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
            capabilities_claim=self.capabilities_claim,
        )

    def _jwk_client(self, jwt_module: JwtModule) -> JwkClient:
        if self.jwk_client_factory is not None:
            return self.jwk_client_factory(self.jwks_url)
        return jwt_module.PyJWKClient(self.jwks_url)


def require_role(principal: ServicePrincipal, role: ServiceRole) -> None:
    """Raise if a principal lacks the required role."""

    if not principal.has_role(role):
        raise ServiceAuthError(f"service role required: {role.value}")


def require_capability(principal: ServicePrincipal, capability: ServiceCapability) -> None:
    """Raise if a principal lacks an explicit service capability."""

    if not principal.has_capability(capability):
        raise ServiceAuthError(f"service capability required: {capability.value}")


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
    capabilities_claim: str,
) -> ServicePrincipal:
    if not isinstance(claims, dict):
        raise ServiceAuthError("invalid service JWT claims")
    principal_id = claims.get(principal_claim)
    if not isinstance(principal_id, str) or not principal_id:
        raise ServiceAuthError("invalid service JWT principal")
    return ServicePrincipal(
        principal_id=principal_id,
        roles=frozenset(_roles_from_claim(claims.get(roles_claim))),
        capabilities=frozenset(_capabilities_from_claim(claims.get(capabilities_claim))),
    )


def _roles_from_claim(value: Any) -> tuple[ServiceRole, ...]:
    if isinstance(value, str):
        raw_roles = tuple(part for part in value.split() if part)
    elif isinstance(value, list):
        if not all(isinstance(role, str) for role in value):
            raise ServiceAuthError("invalid service JWT roles")
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


def _capabilities_from_claim(value: Any) -> tuple[ServiceCapability, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        raw_capabilities = tuple(part for part in value.split() if part)
    elif isinstance(value, list):
        if not all(isinstance(capability, str) for capability in value):
            raise ServiceAuthError("invalid service JWT capabilities")
        raw_capabilities = tuple(capability for capability in value if isinstance(capability, str))
    else:
        raise ServiceAuthError("invalid service JWT capabilities")
    capabilities: list[ServiceCapability] = []
    for raw_capability in raw_capabilities:
        try:
            capabilities.append(ServiceCapability(raw_capability))
        except ValueError as exc:
            raise ServiceAuthError("invalid service JWT capabilities") from exc
    return tuple(capabilities)
