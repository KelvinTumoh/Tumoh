"""Tenant-aware access helpers for the authentication layer."""

from __future__ import annotations

from ide_core.tenant.models import User


def validate_tenant_access(user: User, target_tenant_id: str) -> bool:
    """Return ``True`` if ``user`` is a member of ``target_tenant_id``.

    This is the primary cross-tenant isolation gate.  A user may only
    read, edit, or otherwise interact with resources that belong to the
    tenant explicitly associated with their account.
    """
    if not user or not target_tenant_id:
        return False
    return user.tenant_id == target_tenant_id and user.role in (
        "owner",
        "admin",
        "member",
    )
