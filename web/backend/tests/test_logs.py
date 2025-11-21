"""
Tests for log export endpoints.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest


@pytest.mark.asyncio
async def test_logs_export_success_admin(client, mock_admin_session):
    """Test logs/export endpoint returns file for admin."""
    mock_log_content = b"[2025-11-09 12:00:00] INFO: Bot started\n[2025-11-09 12:01:00] INFO: Command executed\n"

    with patch("core.dependencies.InternalAPIClient.export_logs", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_log_content

        response = await client.get(
            "/api/logs/export",
            cookies={"session": mock_admin_session}
        )

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert "attachment" in response.headers["content-disposition"]
    assert "bot.log.tail.txt" in response.headers["content-disposition"]
    assert response.content == mock_log_content


@pytest.mark.asyncio
async def test_logs_export_with_max_bytes(client, mock_admin_session):
    """Test logs/export endpoint respects max_bytes parameter."""
    mock_log_content = b"Log content"

    with patch("core.dependencies.InternalAPIClient.export_logs", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_log_content

        response = await client.get(
            "/api/logs/export?max_bytes=524288",  # 512KB
            cookies={"session": mock_admin_session}
        )

    assert response.status_code == 200
    # Verify the mock was called with the correct parameter
    mock_get.assert_called_once_with(max_bytes=524288)


@pytest.mark.asyncio
async def test_logs_export_unauthorized(client):
    """Test logs/export endpoint returns 401 without session."""
    response = await client.get("/api/logs/export")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logs_export_forbidden_moderator(client, mock_moderator_session):
    """Test logs/export endpoint returns 403 for moderator."""
    response = await client.get(
        "/api/logs/export",
        cookies={"session": mock_moderator_session}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_logs_export_forbidden_unauthorized(client, mock_unauthorized_session):
    """Test logs/export endpoint returns 403 for unauthorized user."""
    response = await client.get(
        "/api/logs/export",
        cookies={"session": mock_unauthorized_session}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_logs_export_internal_error(client, mock_admin_session):
    """Test logs/export endpoint handles internal API errors."""
    with patch("core.dependencies.InternalAPIClient.export_logs", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.RequestError(
            "Internal API unavailable",
            request=httpx.Request("GET", "http://internal"),
        )

        response = await client.get(
            "/api/logs/export",
            cookies={"session": mock_admin_session}
        )

    assert response.status_code == 503
    assert "Failed to export logs" in response.json()["detail"]


@pytest.mark.asyncio
async def test_logs_export_http_status_error(client, mock_admin_session):
    """HTTP errors from internal API should propagate status code and detail."""
    response_obj = httpx.Response(
        500,
        request=httpx.Request("GET", "http://internal"),
        content=b"{\"detail\": \"internal failure\"}",
    )

    with patch("core.dependencies.InternalAPIClient.export_logs", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.HTTPStatusError(
            "internal failure",
            request=response_obj.request,
            response=response_obj,
        )

        response = await client.get(
            "/api/logs/export",
            cookies={"session": mock_admin_session},
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "internal failure"


@pytest.mark.asyncio
async def test_logs_export_large_file(client, mock_admin_session):
    """Test logs/export endpoint handles large log files."""
    # Generate 2MB of mock log content
    mock_log_content = b"Log line\n" * 200000

    with patch("core.dependencies.InternalAPIClient.export_logs", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_log_content

        response = await client.get(
            "/api/logs/export?max_bytes=2097152",  # 2MB
            cookies={"session": mock_admin_session}
        )

    assert response.status_code == 200
    assert len(response.content) > 0
