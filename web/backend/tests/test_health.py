"""
Tests for health monitoring endpoints.
"""


import httpx
import pytest


@pytest.mark.asyncio
async def test_health_overview_success_admin(client, mock_admin_session, fake_internal_api):
    """Test health overview endpoint returns data for admin."""
    mock_health_data = {
        "status": "healthy",
        "uptime_seconds": 3600,
        "db_ok": True,
        "discord_latency_ms": 45.2,
        "system": {"cpu_percent": 15.5, "memory_percent": 42.3},
    }

    fake_internal_api._health_report_override = mock_health_data

    response = await client.get(
        "/api/health/overview", cookies={"session": mock_admin_session}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["status"] == "healthy"
    assert data["data"]["uptime_seconds"] == 3600
    assert data["data"]["db_ok"] is True
    assert data["data"]["discord_latency_ms"] == 45.2
    assert data["data"]["system"]["cpu_percent"] == 15.5
    assert data["data"]["system"]["memory_percent"] == 42.3


@pytest.mark.asyncio
async def test_health_overview_unauthorized(client):
    """Test health overview endpoint returns 401 without session."""
    response = await client.get("/api/health/overview")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_health_overview_forbidden_moderator(client, mock_moderator_session):
    """Test health overview endpoint returns 403 for moderator."""
    response = await client.get(
        "/api/health/overview", cookies={"session": mock_moderator_session}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_health_overview_forbidden_unauthorized(
    client, mock_unauthorized_session
):
    """Test health overview endpoint returns 403 for unauthorized user."""
    response = await client.get(
        "/api/health/overview", cookies={"session": mock_unauthorized_session}
    )
    assert response.status_code == 400  # User has no authorized guilds


@pytest.mark.asyncio
async def test_health_overview_internal_error(
    client, mock_admin_session, fake_internal_api
):
    """Test health overview endpoint handles internal API errors."""
    fake_internal_api._health_report_override = httpx.RequestError(
        "Internal API unavailable",
        request=httpx.Request("GET", "http://internal"),
    )

    response = await client.get(
        "/api/health/overview", cookies={"session": mock_admin_session}
    )

    assert response.status_code == 503
    assert "Failed to fetch health report" in response.json()["detail"]


@pytest.mark.asyncio
async def test_health_overview_without_latency(
    client, mock_admin_session, fake_internal_api
):
    """Test health overview handles missing optional discord_latency_ms."""
    mock_health_data = {
        "status": "degraded",
        "uptime_seconds": 120,
        "db_ok": False,
        "system": {"cpu_percent": 5.0, "memory_percent": 20.0},
    }

    fake_internal_api._health_report_override = mock_health_data

    response = await client.get(
        "/api/health/overview", cookies={"session": mock_admin_session}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["data"]["discord_latency_ms"] is None
    assert data["data"]["db_ok"] is False


@pytest.mark.asyncio
async def test_health_overview_http_status_error(
    client, mock_admin_session, fake_internal_api
):
    """HTTP errors from internal API propagate status and message."""
    response_obj = httpx.Response(
        502,
        request=httpx.Request("GET", "http://internal"),
        content=b'{"detail": "bot unavailable"}',
    )

    fake_internal_api._health_report_override = httpx.HTTPStatusError(
        "bot unavailable",
        request=response_obj.request,
        response=response_obj,
    )

    response = await client.get(
        "/api/health/overview",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "bot unavailable"
