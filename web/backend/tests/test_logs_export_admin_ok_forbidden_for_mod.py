"""
Tests for logs export endpoint with RBAC enforcement and download headers.
"""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_logs_export_admin_ok(client, mock_admin_session):
    """Test logs export endpoint returns log content with download headers for admin."""
    mock_log_content = b"""2025-11-10 12:00:00 INFO Bot started
2025-11-10 12:01:00 WARNING Rate limit approaching
2025-11-10 12:02:00 ERROR Connection timeout"""

    with patch("core.dependencies.InternalAPIClient.export_logs", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_log_content

        response = await client.get(
            "/api/logs/export?lines=100",
            cookies={"session": mock_admin_session}
        )

    assert response.status_code == 200

    # Verify content type for plain text
    assert response.headers["content-type"] == "text/plain; charset=utf-8"

    # Verify Content-Disposition header for download
    assert "content-disposition" in response.headers
    disposition = response.headers["content-disposition"]
    assert "attachment" in disposition
    assert "filename=" in disposition
    assert ".txt" in disposition

    # Verify content
    content = response.content
    assert b"Bot started" in content
    assert b"Rate limit approaching" in content
    assert b"Connection timeout" in content


@pytest.mark.asyncio
async def test_logs_export_custom_lines(client, mock_admin_session):
    """Test logs export endpoint respects custom line count parameter."""
    mock_log_content = b"2025-11-10 12:00:00 INFO Test log line\n" * 50

    with patch("core.dependencies.InternalAPIClient.export_logs", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_log_content

        response = await client.get(
            "/api/logs/export?lines=50",
            cookies={"session": mock_admin_session}
        )

    assert response.status_code == 200
    # Verify mock was called (InternalAPIClient handles line limit)
    mock_get.assert_called_once()


@pytest.mark.asyncio
async def test_logs_export_empty_logs(client, mock_admin_session):
    """Test logs export endpoint handles empty log content."""
    with patch("core.dependencies.InternalAPIClient.export_logs", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = b""

        response = await client.get(
            "/api/logs/export",
            cookies={"session": mock_admin_session}
        )

    assert response.status_code == 200
    assert response.content == b""


@pytest.mark.asyncio
async def test_logs_export_moderator_forbidden(client, mock_moderator_session):
    """Test logs export endpoint returns 403 for moderator (not admin)."""
    response = await client.get(
        "/api/logs/export",
        cookies={"session": mock_moderator_session}
    )

    assert response.status_code == 403
    data = response.json()
    assert data["success"] is False


@pytest.mark.asyncio
async def test_logs_export_unauthorized_forbidden(client):
    """Test logs export endpoint returns 401 for unauthenticated user."""
    response = await client.get("/api/logs/export")

    assert response.status_code == 401
