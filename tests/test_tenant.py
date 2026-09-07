"""Unit tests for multi-tenant workspace isolation."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import websockets
from websockets.datastructures import Headers

from ide_core.auth.manager import AuthManager
from ide_core.auth.manager import User as AuthUser
from ide_core.auth.tenant_aware import validate_tenant_access
from ide_core.config.settings import IDESettings
from ide_core.diagnostics import DiagnosticManager
from ide_core.document_manager import DocumentManager
from ide_core.server import EditorServer
from ide_core.tenant.manager import TenantManager
from ide_core.tenant.middleware import TenantMiddleware
from ide_core.tenant.models import Invitation, Team, Tenant, User


class FakeLSPClient:
    """Stub LSP client for tenant server tests."""

    did_open = AsyncMock()
    did_change = AsyncMock()
    did_close = AsyncMock()
    completion = AsyncMock(return_value={"result": []})

    def on(self, method: str, callback) -> None:
        pass


def test_ide_settings_multi_tenant_defaults() -> None:
    settings = IDESettings()
    assert settings.enable_multi_tenant is False
    assert settings.tenant_storage_path == ".ide_tenants"
    assert settings.base_domain == "localhost"
    assert settings.tenant_cache_ttl == 300


def test_tenant_models() -> None:
    tenant = Tenant(
        tenant_id="t-1",
        name="Acme",
        subdomain="acme",
        plan="enterprise",
    )
    assert tenant.plan == "enterprise"
    assert tenant.is_active is True

    user = User(
        user_id="u-1",
        username="alice",
        email="alice@example.com",
        tenant_id="t-1",
        role="admin",
    )
    assert user.tenant_id == "t-1"
    assert user.role == "admin"

    team = Team(team_id="tm-1", tenant_id="t-1", name="Engineering")
    assert team.member_ids == []

    invite = Invitation(
        invite_id="i-1",
        tenant_id="t-1",
        email="bob@example.com",
    )
    assert invite.expires_at is None


def test_tenant_manager_lifecycle(tmp_path) -> None:
    settings = IDESettings(tenant_storage_path=str(tmp_path))
    manager = TenantManager(settings)

    tenant = manager.create_tenant("Acme", "acme", plan="pro")
    assert tenant.name == "Acme"
    assert tenant.subdomain == "acme"
    assert tenant.plan == "pro"
    assert (tmp_path / "tenants" / f"{tenant.tenant_id}.json").exists()
    assert manager.workspace_for(tenant.tenant_id).exists()

    loaded = manager.get_tenant(tenant.tenant_id)
    assert loaded is not None
    assert loaded.tenant_id == tenant.tenant_id

    by_subdomain = manager.get_tenant_by_subdomain("acme")
    assert by_subdomain is not None
    assert by_subdomain.tenant_id == tenant.tenant_id

    updated = manager.update_tenant_settings(
        tenant.tenant_id, {"theme": "dark"}
    )
    assert updated.settings["theme"] == "dark"

    tenants = manager.list_tenants()
    assert len(tenants) == 1

    assert manager.delete_tenant(tenant.tenant_id) is True
    assert manager.get_tenant(tenant.tenant_id) is None
    assert not manager.workspace_for(tenant.tenant_id).exists()
    assert manager.list_tenants() == []


def test_tenant_manager_inactive_lookup_ignored(tmp_path) -> None:
    settings = IDESettings(tenant_storage_path=str(tmp_path))
    manager = TenantManager(settings)
    tenant = manager.create_tenant("Acme", "acme")
    tenant.is_active = False
    manager._save(tenant)
    assert manager.get_tenant_by_subdomain("acme") is None


def test_tenant_middleware_resolves_x_tenant_id(tmp_path) -> None:
    settings = IDESettings(
        tenant_storage_path=str(tmp_path),
        enable_multi_tenant=True,
    )
    manager = TenantManager(settings)
    tenant = manager.create_tenant("Acme", "acme")

    middleware = TenantMiddleware(AsyncMock(), manager, settings)
    request = SimpleNamespace(
        headers=Headers([("X-Tenant-ID", tenant.tenant_id)])
    )
    ws = SimpleNamespace(
        request=request,
        close=AsyncMock(),
    )

    asyncio.run(middleware(ws))
    assert ws.tenant_id == tenant.tenant_id
    assert ws.tenant.tenant_id == tenant.tenant_id


def test_tenant_middleware_resolves_subdomain(tmp_path) -> None:
    settings = IDESettings(
        tenant_storage_path=str(tmp_path),
        base_domain="localhost",
        enable_multi_tenant=True,
    )
    manager = TenantManager(settings)
    tenant = manager.create_tenant("Acme", "acme")

    middleware = TenantMiddleware(AsyncMock(), manager, settings)
    request = SimpleNamespace(
        headers=Headers([("Host", "acme.localhost:8765")])
    )
    ws = SimpleNamespace(
        request=request,
        close=AsyncMock(),
    )

    asyncio.run(middleware(ws))
    assert ws.tenant_id == tenant.tenant_id


def test_tenant_middleware_rejects_invalid_tenant(tmp_path) -> None:
    settings = IDESettings(
        tenant_storage_path=str(tmp_path),
        enable_multi_tenant=True,
    )
    manager = TenantManager(settings)
    middleware = TenantMiddleware(AsyncMock(), manager, settings)

    request = SimpleNamespace(
        headers=Headers([("X-Tenant-ID", "missing")])
    )
    response = asyncio.run(middleware.process_request(None, request))
    assert response is not None
    assert response.status_code == 401


def test_tenant_middleware_rejects_inactive_tenant(tmp_path) -> None:
    settings = IDESettings(
        tenant_storage_path=str(tmp_path),
        enable_multi_tenant=True,
    )
    manager = TenantManager(settings)
    tenant = manager.create_tenant("Acme", "acme")
    tenant.is_active = False
    manager._save(tenant)

    middleware = TenantMiddleware(AsyncMock(), manager, settings)
    request = SimpleNamespace(
        headers=Headers([("X-Tenant-ID", tenant.tenant_id)])
    )
    response = asyncio.run(middleware.process_request(None, request))
    assert response is not None
    assert response.status_code == 403


def test_tenant_middleware_disabled_allows_all(tmp_path) -> None:
    settings = IDESettings(
        tenant_storage_path=str(tmp_path),
        enable_multi_tenant=False,
    )
    manager = TenantManager(settings)
    middleware = TenantMiddleware(AsyncMock(), manager, settings)

    request = SimpleNamespace(headers=Headers())
    response = asyncio.run(middleware.process_request(None, request))
    assert response is None

    handler = AsyncMock()
    middleware2 = TenantMiddleware(handler, manager, settings)
    ws = SimpleNamespace(request=request, close=AsyncMock())
    asyncio.run(middleware2(ws))
    assert ws.tenant is None
    assert ws.tenant_id is None
    handler.assert_awaited_once_with(ws)


def test_auth_token_carries_tenant_and_role() -> None:
    auth = AuthManager()
    user = AuthUser(
        user_id="u-1",
        name="Alice",
        role="admin",
        tenant_id="t-1",
    )
    token = auth.create_token(user)
    loaded = auth.verify_token(token)
    assert loaded is not None
    assert loaded.tenant_id == "t-1"
    assert loaded.role == "admin"


def test_validate_tenant_access() -> None:
    user = User(
        user_id="u-1",
        username="alice",
        email="alice@example.com",
        tenant_id="t-1",
        role="member",
    )
    assert validate_tenant_access(user, "t-1") is True
    assert validate_tenant_access(user, "t-2") is False

    other = User(
        user_id="u-2",
        username="bob",
        email="bob@example.com",
        tenant_id="t-2",
        role="member",
    )
    assert validate_tenant_access(other, "t-1") is False


def test_editor_server_isolates_documents_by_tenant(tmp_path) -> None:
    async def coro() -> None:
        settings = IDESettings(
            tenant_storage_path=str(tmp_path),
            enable_multi_tenant=True,
        )
        manager = TenantManager(settings)
        tenant_a = manager.create_tenant("Tenant A", "tenant-a")
        tenant_b = manager.create_tenant("Tenant B", "tenant-b")

        lsp = FakeLSPClient()
        diagnostics = DiagnosticManager()
        documents = DocumentManager(lsp, diagnostics)
        server = EditorServer(
            lsp_client=lsp,
            document_manager=documents,
            diagnostic_manager=diagnostics,
            port=0,
            settings=settings,
            tenant_manager=manager,
        )
        await server.start()

        try:
            uri = f"ws://localhost:{server.port}"
            async with websockets.connect(
                uri,
                additional_headers={"X-Tenant-ID": tenant_a.tenant_id},
            ) as ws_a:
                await ws_a.send(
                    json.dumps(
                        {
                            "type": "doc_open",
                            "uri": "file:///a.py",
                            "language_id": "python",
                            "content": "hello a",
                        }
                    )
                )
                opened = json.loads(await ws_a.recv())
                assert opened["type"] == "doc_opened"

                async with websockets.connect(
                    uri,
                    additional_headers={"X-Tenant-ID": tenant_b.tenant_id},
                ) as ws_b:
                    await ws_b.send(
                        json.dumps(
                            {
                                "type": "doc_open",
                                "uri": "file:///a.py",
                                "language_id": "python",
                                "content": "hello b",
                            }
                        )
                    )
                    assert json.loads(await ws_b.recv())["type"] == "doc_opened"

                    await ws_b.send(
                        json.dumps(
                            {
                                "type": "doc_edit",
                                "uri": "file:///a.py",
                                "start_index": 6,
                                "end_index": 7,
                                "new_text": "B",
                            }
                        )
                    )
                    sync_b = json.loads(await ws_b.recv())
                    assert sync_b["type"] == "doc_sync"
                    assert sync_b["text"] == "hello B"

                await ws_a.send(
                    json.dumps(
                        {
                            "type": "doc_edit",
                            "uri": "file:///a.py",
                            "start_index": 6,
                            "end_index": 7,
                            "new_text": "A",
                        }
                    )
                )
                sync_a = json.loads(await ws_a.recv())
                assert sync_a["type"] == "doc_sync"
                assert sync_a["text"] == "hello A"

        finally:
            await server.stop()

    asyncio.run(coro())


def test_editor_server_rejects_unknown_tenant(tmp_path) -> None:
    async def coro() -> None:
        settings = IDESettings(
            tenant_storage_path=str(tmp_path),
            enable_multi_tenant=True,
        )
        manager = TenantManager(settings)

        lsp = FakeLSPClient()
        diagnostics = DiagnosticManager()
        documents = DocumentManager(lsp, diagnostics)
        server = EditorServer(
            lsp_client=lsp,
            document_manager=documents,
            diagnostic_manager=diagnostics,
            port=0,
            settings=settings,
            tenant_manager=manager,
        )
        await server.start()

        try:
            with pytest.raises(websockets.InvalidStatus):
                async with websockets.connect(
                    f"ws://localhost:{server.port}",
                    additional_headers={"X-Tenant-ID": "missing"},
                ):
                    pass
        finally:
            await server.stop()

    asyncio.run(coro())
