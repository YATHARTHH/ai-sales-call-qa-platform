"""Unit tests for principal authentication, debug headers, and role elevation prevention."""

import pytest
from fastapi import HTTPException

from apps.api.dependencies import get_current_principal
from packages.infrastructure.config.settings import settings


class DummyRequest:
    """Mock request object for testing dependency extraction."""

    def __init__(self, headers: dict[str, str] | None = None):
        self.headers = headers or {}


@pytest.mark.asyncio
async def test_debug_headers_allowed_in_local_environment(monkeypatch):
    """In local environment, X-Debug-* headers can set user and tenant context."""
    monkeypatch.setattr(settings, "app_env", "local")

    req = DummyRequest(
        headers={
            "x-debug-tenant-id": "retailer-cimet-01",
            "x-debug-user-id": "qa-analyst-1",
            "x-debug-roles": "qa_auditor",
        }
    )
    principal = await get_current_principal(
        request=req,
        debug_tenant_id="retailer-cimet-01",
        debug_user_id="qa-analyst-1",
        debug_roles="qa_auditor",
    )

    assert principal.tenant_id == "retailer-cimet-01"
    assert principal.user_id == "qa-analyst-1"
    assert "qa_auditor" in principal.roles
    assert not principal.is_superadmin


@pytest.mark.asyncio
async def test_cannot_elevate_to_superadmin_via_headers(monkeypatch):
    """Clients cannot self-assign superadmin role via debug headers even in local mode."""
    monkeypatch.setattr(settings, "app_env", "local")

    req = DummyRequest(headers={"x-debug-roles": "superadmin,qa_auditor"})

    with pytest.raises(HTTPException) as exc_info:
        await get_current_principal(
            request=req,
            debug_roles="superadmin,qa_auditor",
        )

    assert exc_info.value.status_code == 403
    assert "superadmin" in exc_info.value.detail


@pytest.mark.asyncio
async def test_debug_headers_strictly_rejected_in_production(monkeypatch):
    """In production/staging environments, any X-Debug-* header must result in 401 Unauthorized."""
    monkeypatch.setattr(settings, "app_env", "production")

    req = DummyRequest(
        headers={
            "x-debug-tenant-id": "retailer-cimet-01",
            "authorization": "Bearer valid-token",
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_current_principal(
            request=req,
            authorization="Bearer valid-token",
            debug_tenant_id="retailer-cimet-01",
        )

    assert exc_info.value.status_code == 401
    assert "Debug authentication headers are strictly prohibited" in exc_info.value.detail


@pytest.mark.asyncio
async def test_production_mode_requires_bearer_token(monkeypatch):
    """In production mode without debug headers, Authorization Bearer token is required."""
    monkeypatch.setattr(settings, "app_env", "production")

    req = DummyRequest(headers={})

    with pytest.raises(HTTPException) as exc_info:
        await get_current_principal(
            request=req,
            authorization=None,
        )

    assert exc_info.value.status_code == 401
    assert "Missing or invalid Authorization bearer token" in exc_info.value.detail


@pytest.mark.asyncio
async def test_production_mode_valid_token(monkeypatch):
    """In production mode with valid bearer token, returns production principal."""
    monkeypatch.setattr(settings, "app_env", "production")

    req = DummyRequest(headers={"authorization": "Bearer valid-prod-token"})

    principal = await get_current_principal(
        request=req,
        authorization="Bearer valid-prod-token",
    )

    assert principal.user_id == "prod-user-001"
    assert principal.tenant_id == "retailer-prod-001"
    assert "qa_auditor" in principal.roles
