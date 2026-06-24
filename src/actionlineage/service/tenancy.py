"""Dependency-free tenant authorization primitives for optional service mode."""

from __future__ import annotations

from dataclasses import dataclass

from actionlineage.service.auth import (
    ServiceAuthError,
    ServicePrincipal,
    ServiceRole,
    _roles_grant,
)


@dataclass(frozen=True, slots=True)
class ServiceTenant:
    """One service tenant namespace."""

    tenant_id: str
    display_name: str
    tags: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible tenant object."""

        return {
            "tenant_id": self.tenant_id,
            "display_name": self.display_name,
            "tags": list(self.tags),
        }


@dataclass(frozen=True, slots=True)
class TenantRoleBinding:
    """Role binding for one principal inside one tenant."""

    tenant_id: str
    principal_id: str
    roles: frozenset[ServiceRole]

    def __post_init__(self) -> None:
        object.__setattr__(self, "roles", frozenset(self.roles))

    def has_role(self, required: ServiceRole) -> bool:
        """Return true when the binding grants at least the requested role."""

        return _roles_grant(self.roles, required)

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible binding without credentials."""

        return {
            "tenant_id": self.tenant_id,
            "principal_id": self.principal_id,
            "roles": sorted(role.value for role in self.roles),
        }


@dataclass(frozen=True, slots=True)
class TenantAccessDecision:
    """Machine-readable tenant authorization decision."""

    tenant_id: str
    principal_id: str
    required_role: ServiceRole
    allowed: bool
    reason: str

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible access decision."""

        return {
            "tenant_id": self.tenant_id,
            "principal_id": self.principal_id,
            "required_role": self.required_role.value,
            "allowed": self.allowed,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class TenantRegistry:
    """In-memory tenant registry for local or optional service deployments."""

    tenants: tuple[ServiceTenant, ...]
    bindings: tuple[TenantRoleBinding, ...]

    def decide(
        self,
        principal: ServicePrincipal,
        *,
        tenant_id: str,
        required_role: ServiceRole,
    ) -> TenantAccessDecision:
        """Return a tenant-scoped authorization decision."""

        if tenant_id not in self._tenant_ids():
            return TenantAccessDecision(
                tenant_id=tenant_id,
                principal_id=principal.principal_id,
                required_role=required_role,
                allowed=False,
                reason="tenant_unknown",
            )
        if not principal.has_role(required_role):
            return TenantAccessDecision(
                tenant_id=tenant_id,
                principal_id=principal.principal_id,
                required_role=required_role,
                allowed=False,
                reason="principal_role_missing",
            )
        for binding in self.bindings:
            if binding.tenant_id != tenant_id or binding.principal_id != principal.principal_id:
                continue
            if binding.has_role(required_role):
                return TenantAccessDecision(
                    tenant_id=tenant_id,
                    principal_id=principal.principal_id,
                    required_role=required_role,
                    allowed=True,
                    reason="tenant_role_granted",
                )
        return TenantAccessDecision(
            tenant_id=tenant_id,
            principal_id=principal.principal_id,
            required_role=required_role,
            allowed=False,
            reason="tenant_binding_missing",
        )

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible tenant registry summary."""

        return {
            "tenants": [tenant.as_dict() for tenant in self.tenants],
            "bindings": [binding.as_dict() for binding in self.bindings],
        }

    def _tenant_ids(self) -> frozenset[str]:
        return frozenset(tenant.tenant_id for tenant in self.tenants)


def require_tenant_role(
    registry: TenantRegistry,
    principal: ServicePrincipal,
    *,
    tenant_id: str,
    role: ServiceRole,
) -> TenantAccessDecision:
    """Raise if the principal lacks the required tenant-scoped role."""

    decision = registry.decide(principal, tenant_id=tenant_id, required_role=role)
    if not decision.allowed:
        raise ServiceAuthError(f"tenant service role required: {tenant_id}:{role.value}")
    return decision
