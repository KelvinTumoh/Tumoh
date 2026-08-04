"""File-backed tenant storage and management."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Optional

from ide_core.config.settings import IDESettings
from ide_core.tenant.models import Tenant


class TenantManager:
    """Persist and manage tenants in a local JSON file store."""

    def __init__(self, settings: Optional[IDESettings] = None) -> None:
        self._settings = settings or IDESettings()
        self._root = Path(self._settings.tenant_storage_path)
        self._tenants_dir = self._root / "tenants"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        """Create the tenant storage directories if they do not exist."""
        self._tenants_dir.mkdir(parents=True, exist_ok=True)

    def _tenant_path(self, tenant_id: str) -> Path:
        """Return the JSON file path for a given tenant."""
        return self._tenants_dir / f"{tenant_id}.json"

    def _workspace_path(self, tenant_id: str) -> Path:
        """Return the isolated workspace directory for a given tenant."""
        return self._root / tenant_id / "workspace"

    def _save(self, tenant: Tenant) -> None:
        """Serialize a tenant to its JSON file."""
        path = self._tenant_path(tenant.tenant_id)
        path.write_text(
            tenant.model_dump_json(indent=2, by_alias=True), encoding="utf-8"
        )

    def create_tenant(
        self, name: str, subdomain: str, plan: str = "free"
    ) -> Tenant:
        """Create a new tenant and provision its isolated workspace."""
        tenant_id = uuid.uuid4().hex
        tenant = Tenant(
            tenant_id=tenant_id,
            name=name,
            subdomain=subdomain,
            plan=plan,  # type: ignore[arg-type]
        )
        self._save(tenant)
        self._workspace_path(tenant_id).mkdir(parents=True, exist_ok=True)
        return tenant

    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """Return a tenant by ID, or ``None`` if not found."""
        path = self._tenant_path(tenant_id)
        if not path.exists():
            return None
        try:
            return Tenant.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, ValueError):
            return None

    def get_tenant_by_subdomain(self, subdomain: str) -> Optional[Tenant]:
        """Return the active tenant matching ``subdomain``."""
        for tenant in self.list_tenants():
            if tenant.subdomain == subdomain and tenant.is_active:
                return tenant
        return None

    def update_tenant_settings(
        self, tenant_id: str, settings: dict
    ) -> Tenant:
        """Merge new settings into an existing tenant and persist it."""
        tenant = self.get_tenant(tenant_id)
        if tenant is None:
            raise KeyError(f"Tenant not found: {tenant_id}")
        tenant.settings = {**tenant.settings, **settings}
        self._save(tenant)
        return tenant

    def delete_tenant(self, tenant_id: str) -> bool:
        """Delete a tenant and its workspace. Returns ``True`` on success."""
        path = self._tenant_path(tenant_id)
        if not path.exists():
            return False
        path.unlink()
        workspace = self._root / tenant_id
        if workspace.exists():
            shutil.rmtree(workspace)
        return True

    def list_tenants(self) -> list[Tenant]:
        """Return all stored tenants, skipping corrupt files."""
        tenants: list[Tenant] = []
        for path in self._tenants_dir.glob("*.json"):
            try:
                tenant = Tenant.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except (json.JSONDecodeError, ValueError):
                continue
            tenants.append(tenant)
        return tenants

    def workspace_for(self, tenant_id: str) -> Path:
        """Return the workspace directory for a tenant."""
        return self._workspace_path(tenant_id)

    def resolve_tenant(
        self,
        tenant_id: Optional[str] = None,
        subdomain: Optional[str] = None,
    ) -> Optional[Tenant]:
        """Resolve a tenant from an explicit ID or a subdomain."""
        if tenant_id:
            return self.get_tenant(tenant_id)
        if subdomain:
            return self.get_tenant_by_subdomain(subdomain)
        return None
