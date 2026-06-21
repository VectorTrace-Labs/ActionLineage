"""Optional service mode helpers."""

from actionlineage.service.api import ServiceDependencyError, create_app
from actionlineage.service.auth import (
    JwtAuthenticator,
    JwtLibraryUnavailable,
    OidcJwtAuthenticator,
    ServiceAuthError,
    ServicePrincipal,
    ServiceRole,
    StaticTokenAuthenticator,
    require_role,
)
from actionlineage.service.health import HealthIssue, HealthReport, HealthState, check_local_health
from actionlineage.service.runtime import (
    DEFAULT_DATABASE_PATH,
    DEFAULT_EXPORT_ROOT,
    DEFAULT_JOURNAL_PATH,
    ServiceRuntimeConfigError,
    create_service_app_from_env,
)
from actionlineage.service.tenancy import (
    ServiceTenant,
    TenantAccessDecision,
    TenantRegistry,
    TenantRoleBinding,
    require_tenant_role,
)

__all__ = [
    "DEFAULT_DATABASE_PATH",
    "DEFAULT_EXPORT_ROOT",
    "DEFAULT_JOURNAL_PATH",
    "HealthIssue",
    "HealthReport",
    "HealthState",
    "JwtAuthenticator",
    "JwtLibraryUnavailable",
    "OidcJwtAuthenticator",
    "ServiceAuthError",
    "ServiceDependencyError",
    "ServicePrincipal",
    "ServiceRole",
    "ServiceRuntimeConfigError",
    "ServiceTenant",
    "StaticTokenAuthenticator",
    "TenantAccessDecision",
    "TenantRegistry",
    "TenantRoleBinding",
    "check_local_health",
    "create_app",
    "create_service_app_from_env",
    "require_role",
    "require_tenant_role",
]
