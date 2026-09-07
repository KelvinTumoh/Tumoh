"""Tenant resolution middleware for WebSocket connections."""

from __future__ import annotations

from typing import Any

import websockets
from websockets.datastructures import Headers
from websockets.http11 import Request, Response

from ide_core.config.settings import IDESettings
from ide_core.tenant.manager import TenantManager
from ide_core.tenant.models import Tenant


class TenantMiddleware:
    """Resolve a tenant from incoming headers and attach it to a WebSocket.

    The middleware extracts a tenant identifier from either the
    ``X-Tenant-ID`` request header or the request's ``Host`` subdomain
    (``company-a.localhost:8000`` becomes ``company-a``).  When multi-tenancy
    is enabled, invalid or inactive tenants are rejected with an HTTP
    401/403 response before the WebSocket handshake completes.
    """

    def __init__(
        self,
        handler,
        tenant_manager: TenantManager,
        settings: IDESettings | None = None,
    ) -> None:
        self._handler = handler
        self._manager = tenant_manager
        self._settings = settings or IDESettings()

    async def __call__(self, ws: websockets.ServerConnection, *args: Any) -> None:
        """Resolve the tenant, attach it to ``ws``, and call the handler."""
        tenant = self._resolve(ws)

        if tenant is None and self._settings.enable_multi_tenant:
            await ws.close(
                code=3401,
                reason="Unauthorized: missing or invalid tenant",
            )
            return

        ws.tenant = tenant  # type: ignore[attr-defined]
        ws.tenant_id = (  # type: ignore[attr-defined]
            tenant.tenant_id if tenant is not None else None
        )
        await self._handler(ws, *args)

    async def process_request(
        self,
        connection: websockets.ServerConnection,
        request: Request,
    ) -> Response | None:
        """Validate the tenant before the WebSocket handshake completes."""
        if not self._settings.enable_multi_tenant:
            return None
        headers = request.headers
        tenant_id = headers.get("X-Tenant-ID")
        host = headers.get("Host")
        subdomain = self._subdomain_from_host(host) if host else None
        tenant = self._manager.resolve_tenant(
            tenant_id=tenant_id, subdomain=subdomain
        )
        if tenant is None:
            return Response(
                status_code=401,
                reason_phrase="Unauthorized",
                headers=Headers(),
                body=b"Unauthorized: missing or invalid tenant",
            )
        if not tenant.is_active:
            return Response(
                status_code=403,
                reason_phrase="Forbidden",
                headers=Headers(),
                body=b"Forbidden: inactive tenant",
            )
        return None

    def _resolve(
        self, ws: websockets.ServerConnection
    ) -> Tenant | None:
        """Look up a tenant from ``X-Tenant-ID`` or the ``Host`` subdomain."""
        request = getattr(ws, "request", None)
        if request is None:
            return None
        headers = getattr(request, "headers", {})
        if not headers:
            return None

        tenant_id = headers.get("X-Tenant-ID")
        host = headers.get("Host")
        subdomain = self._subdomain_from_host(host) if host else None

        if not tenant_id and not subdomain:
            return None

        tenant = self._manager.resolve_tenant(
            tenant_id=tenant_id, subdomain=subdomain
        )
        if tenant is None or not tenant.is_active:
            return None
        return tenant

    def _subdomain_from_host(self, host: str) -> str | None:
        """Extract the subdomain when the host ends with ``base_domain``."""
        host_part = host.split(":", 1)[0]
        base = f".{self._settings.base_domain}"
        if host_part.endswith(base):
            return host_part[: -len(base)]
        return None
