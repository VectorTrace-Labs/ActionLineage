"""Dependency-free tenant authorization primitives for optional service mode."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from actionlineage.service.auth import (
    ServiceAuthError,
    ServicePrincipal,
    ServiceRole,
    _roles_grant,
)

TENANT_STORAGE_LAYOUT_VERSION = "actionlineage.dev/tenant-storage-layout-v1"
TENANT_ID_MAX_LENGTH = 128
TENANT_ID_ALLOWED_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
)


class TenantIsolationError(ValueError):
    """Raised when a tenant boundary or path scope is invalid."""


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
class TenantStorageScope:
    """Storage, query, export, log, cache, and anchor paths for one tenant."""

    tenant_id: str
    journal_path: Path
    database_path: Path
    export_root: Path
    service_log_path: Path
    cache_root: Path
    anchor_root: Path
    anchor_path: Path
    anchor_log_path: Path
    layout_version: str = TENANT_STORAGE_LAYOUT_VERSION

    def export_dir(self, requested_output_dir: str) -> Path:
        """Return a confined case-export directory below this tenant's export root."""

        return confined_service_path(
            self.export_root,
            requested_output_dir,
            field_name="output_dir",
        )

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible storage-scope summary."""

        return {
            "layout_version": self.layout_version,
            "tenant_id": self.tenant_id,
            "journal_path": str(self.journal_path),
            "database_path": str(self.database_path),
            "export_root": str(self.export_root),
            "service_log_path": str(self.service_log_path),
            "cache_root": str(self.cache_root),
            "anchor_root": str(self.anchor_root),
            "anchor_path": str(self.anchor_path),
            "anchor_log_path": str(self.anchor_log_path),
        }


@dataclass(frozen=True, slots=True)
class TenantStorageLayout:
    """Configured filesystem roots for tenant-isolated optional service state."""

    journal_root: Path
    database_root: Path
    export_root: Path
    log_root: Path
    cache_root: Path
    anchor_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "journal_root", Path(self.journal_root))
        object.__setattr__(self, "database_root", Path(self.database_root))
        object.__setattr__(self, "export_root", Path(self.export_root))
        object.__setattr__(self, "log_root", Path(self.log_root))
        object.__setattr__(self, "cache_root", Path(self.cache_root))
        object.__setattr__(self, "anchor_root", Path(self.anchor_root))

    @classmethod
    def under_base(cls, base_path: Path) -> TenantStorageLayout:
        """Create the standard local layout under one base directory."""

        base = Path(base_path)
        return cls(
            journal_root=base / "journals",
            database_root=base / "projections",
            export_root=base / "exports",
            log_root=base / "logs",
            cache_root=base / "caches",
            anchor_root=base / "anchors",
        )

    def scope_for(self, tenant_id: str) -> TenantStorageScope:
        """Return path scope for a syntactically valid tenant ID."""

        tenant_segment = validate_tenant_id(tenant_id)
        anchor_root = _tenant_child(self.anchor_root, tenant_segment)
        return TenantStorageScope(
            tenant_id=tenant_segment,
            journal_path=_tenant_child(self.journal_root, tenant_segment, "actionlineage.journal"),
            database_path=_tenant_child(self.database_root, tenant_segment, "projection.sqlite"),
            export_root=_tenant_child(self.export_root, tenant_segment),
            service_log_path=_tenant_child(self.log_root, tenant_segment, "service.ndjson"),
            cache_root=_tenant_child(self.cache_root, tenant_segment),
            anchor_root=anchor_root,
            anchor_path=anchor_root / "journal-anchor.json",
            anchor_log_path=anchor_root / "anchor-log.jsonl",
        )

    def as_dict(self) -> dict[str, object]:
        """Return configured tenant layout roots without tenant secrets."""

        return {
            "layout_version": TENANT_STORAGE_LAYOUT_VERSION,
            "journal_root": str(self.journal_root),
            "database_root": str(self.database_root),
            "export_root": str(self.export_root),
            "log_root": str(self.log_root),
            "cache_root": str(self.cache_root),
            "anchor_root": str(self.anchor_root),
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

    def storage_scope(
        self,
        layout: TenantStorageLayout,
        *,
        tenant_id: str,
    ) -> TenantStorageScope:
        """Return the storage scope for a known tenant."""

        tenant_segment = validate_tenant_id(tenant_id)
        if tenant_segment not in self._tenant_ids():
            raise ServiceAuthError(f"tenant storage scope required: {tenant_segment}")
        return layout.scope_for(tenant_segment)

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
        raise ServiceAuthError(
            f"tenant service role required: {tenant_id}:{role.value} ({decision.reason})"
        )
    return decision


def require_tenant_storage_scope(
    registry: TenantRegistry,
    principal: ServicePrincipal,
    *,
    tenant_id: str,
    role: ServiceRole,
    layout: TenantStorageLayout,
) -> TenantStorageScope:
    """Authorize and return the tenant's isolated storage scope."""

    require_tenant_role(registry, principal, tenant_id=tenant_id, role=role)
    return registry.storage_scope(layout, tenant_id=tenant_id)


def validate_tenant_id(tenant_id: str) -> str:
    """Validate a tenant ID as a single portable storage path segment."""

    if not tenant_id:
        raise TenantIsolationError("tenant_id is required")
    if len(tenant_id) > TENANT_ID_MAX_LENGTH:
        raise TenantIsolationError("tenant_id is too long")
    if tenant_id in {".", ".."}:
        raise TenantIsolationError("tenant_id must be a single path segment")
    if any(character not in TENANT_ID_ALLOWED_CHARS for character in tenant_id):
        raise TenantIsolationError("tenant_id contains unsupported characters")
    return tenant_id


def confined_service_path(root: Path, requested_relative_path: str, *, field_name: str) -> Path:
    """Return a path below root for a relative service request path."""

    if not requested_relative_path.strip():
        raise ValueError(f"{field_name} must be a relative path under its configured root")

    requested = Path(requested_relative_path)
    if requested.is_absolute() or any(part in {"", ".", ".."} for part in requested.parts):
        raise ValueError(f"{field_name} must be a relative path under its configured root")

    root_path = Path(root).resolve(strict=False)
    candidate = (root_path / requested).resolve(strict=False)
    if candidate == root_path or not candidate.is_relative_to(root_path):
        raise ValueError(f"{field_name} must stay under its configured root")
    return candidate


def _tenant_child(root: Path, tenant_id: str, *parts: str) -> Path:
    root_path = Path(root).resolve(strict=False)
    tenant_root = (root_path / tenant_id).resolve(strict=False)
    candidate = (tenant_root / Path(*parts)).resolve(strict=False) if parts else tenant_root
    if not candidate.is_relative_to(tenant_root):
        raise TenantIsolationError("tenant path escaped tenant storage root")
    return candidate
