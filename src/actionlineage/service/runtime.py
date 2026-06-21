"""Environment-driven optional service runtime factory."""

from __future__ import annotations

import os
from pathlib import Path

from actionlineage.service.api import create_app
from actionlineage.service.auth import ServicePrincipal, ServiceRole, StaticTokenAuthenticator

DEFAULT_JOURNAL_PATH = Path("/data/actionlineage.journal")
DEFAULT_DATABASE_PATH = Path("/data/projection.sqlite")


class ServiceRuntimeConfigError(RuntimeError):
    """Raised when service runtime environment is incomplete."""


def create_service_app_from_env() -> object:
    """Create the optional service app from environment variables.

    Intended for Uvicorn's ``--factory`` mode. The bearer token must be supplied
    by the runtime environment; deployment examples use a local placeholder that
    operators must replace before production.
    """

    token = os.environ.get("ACTIONLINEAGE_SERVICE_TOKEN")
    if not token:
        raise ServiceRuntimeConfigError("ACTIONLINEAGE_SERVICE_TOKEN is required")

    journal_path = Path(os.environ.get("ACTIONLINEAGE_JOURNAL_PATH", str(DEFAULT_JOURNAL_PATH)))
    database_path = Path(os.environ.get("ACTIONLINEAGE_DATABASE_PATH", str(DEFAULT_DATABASE_PATH)))
    principal_id = os.environ.get("ACTIONLINEAGE_SERVICE_PRINCIPAL", "service-admin")
    roles = _roles_from_env(os.environ.get("ACTIONLINEAGE_SERVICE_ROLES", "admin"))

    return create_app(
        journal_path=journal_path,
        database_path=database_path,
        authenticator=StaticTokenAuthenticator(
            tokens={
                token: ServicePrincipal(
                    principal_id=principal_id,
                    roles=roles,
                )
            }
        ),
    )


def _roles_from_env(value: str) -> frozenset[ServiceRole]:
    roles: set[ServiceRole] = set()
    for item in value.split(","):
        normalized = item.strip().lower()
        if not normalized:
            continue
        try:
            roles.add(ServiceRole(normalized))
        except ValueError as exc:
            raise ServiceRuntimeConfigError(f"unsupported service role: {normalized}") from exc
    if not roles:
        raise ServiceRuntimeConfigError(
            "ACTIONLINEAGE_SERVICE_ROLES must include at least one role"
        )
    return frozenset(roles)
