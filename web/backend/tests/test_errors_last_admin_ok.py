"""
Tests for errors last endpoint with RBAC enforcement.
"""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_errors_last_admin_ok(client, mock_admin_session):
    """Test errors last endpoint returns structured errors for admin."""
    mock_errors = {
        "errors": [
            {
                "time": "2025-11-10T12:00:00Z",
                "error_type": "ValueError",
                "component": "cogs.verification",
                "message": "Invalid RSI handle format",
                "traceback": "Traceback (most recent call last):\n  ..."
            }
        ]
    }
    
    with patch("core.dependencies.InternalAPIClient.get_last_errors", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_errors
        
        response = await client.get(
            "/api/errors/last?limit=1",
            cookies={"session": mock_admin_session}
        )
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify response structure
    assert data["success"] is True
    assert "errors" in data
    assert len(data["errors"]) == 1
    
    # Verify error structure
    error = data["errors"][0]
    assert error["time"] == "2025-11-10T12:00:00Z"
    assert error["error_type"] == "ValueError"
    assert error["component"] == "cogs.verification"
    assert error["message"] == "Invalid RSI handle format"
    assert "traceback" in error


@pytest.mark.asyncio
async def test_errors_last_multiple_errors(client, mock_admin_session):
    """Test errors last endpoint handles multiple errors correctly."""
    mock_errors = {
        "errors": [
            {
                "time": "2025-11-10T12:01:00Z",
                "error_type": "TypeError",
                "component": "helpers.discord_api",
                "message": "Expected int, got str"
            },
            {
                "time": "2025-11-10T12:00:00Z",
                "error_type": "KeyError",
                "component": "services.voice_service",
                "message": "Missing channel_id"
            }
        ]
    }
    
    with patch("core.dependencies.InternalAPIClient.get_last_errors", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_errors
        
        response = await client.get(
            "/api/errors/last?limit=5",
            cookies={"session": mock_admin_session}
        )
    
    assert response.status_code == 200
    errors = response.json()["errors"]
    assert len(errors) == 2
    assert errors[0]["error_type"] == "TypeError"
    assert errors[1]["error_type"] == "KeyError"


@pytest.mark.asyncio
async def test_errors_last_empty_list(client, mock_admin_session):
    """Test errors last endpoint handles empty error list."""
    with patch("core.dependencies.InternalAPIClient.get_last_errors", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"errors": []}
        
        response = await client.get(
            "/api/errors/last",
            cookies={"session": mock_admin_session}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_errors_last_moderator_forbidden(client, mock_moderator_session):
    """Test errors last endpoint returns 403 for moderator (not admin)."""
    response = await client.get(
        "/api/errors/last",
        cookies={"session": mock_moderator_session}
    )
    
    assert response.status_code == 403
