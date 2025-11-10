"""
Tests for health overview endpoint with RBAC enforcement.
"""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_health_overview_admin_ok(client, mock_admin_session):
    """Test health overview endpoint returns data for admin with proper shape."""
    mock_health_data = {
        "status": "healthy",
        "uptime_seconds": 3600,
        "db_ok": True,
        "discord_latency_ms": 25.0,
        "system": {
            "cpu_percent": 5.0,
            "memory_percent": 10.0
        }
    }
    
    with patch("core.dependencies.InternalAPIClient.get_health_report", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_health_data
        
        response = await client.get(
            "/api/health/overview",
            cookies={"session": mock_admin_session}
        )
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify response structure
    assert data["success"] is True
    assert "data" in data
    
    # Verify health overview shape
    health = data["data"]
    assert health["status"] == "healthy"
    assert health["uptime_seconds"] == 3600
    assert health["db_ok"] is True
    assert health["discord_latency_ms"] == 25.0
    assert "system" in health
    assert health["system"]["cpu_percent"] == 5.0
    assert health["system"]["memory_percent"] == 10.0


@pytest.mark.asyncio
async def test_health_overview_degraded_status(client, mock_admin_session):
    """Test health overview handles degraded status correctly."""
    mock_health_data = {
        "status": "degraded",
        "uptime_seconds": 120,
        "db_ok": False,
        "discord_latency_ms": 150.5,
        "system": {
            "cpu_percent": 85.5,
            "memory_percent": 90.2
        }
    }
    
    with patch("core.dependencies.InternalAPIClient.get_health_report", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_health_data
        
        response = await client.get(
            "/api/health/overview",
            cookies={"session": mock_admin_session}
        )
    
    assert response.status_code == 200
    health = response.json()["data"]
    assert health["status"] == "degraded"
    assert health["db_ok"] is False
    assert health["system"]["cpu_percent"] == 85.5
