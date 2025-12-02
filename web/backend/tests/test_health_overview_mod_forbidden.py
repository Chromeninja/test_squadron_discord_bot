"""
Tests for health overview endpoint RBAC - moderator access should be forbidden.
"""

import pytest


@pytest.mark.asyncio
async def test_health_overview_moderator_forbidden(client, mock_moderator_session):
    """Test health overview endpoint returns 403 for moderator (not admin)."""
    response = await client.get(
        "/api/health/overview", cookies={"session": mock_moderator_session}
    )

    assert response.status_code == 403
    data = response.json()
    assert data["success"] is False
    assert "error" in data or "detail" in data


@pytest.mark.asyncio
async def test_health_overview_unauthorized_forbidden(client):
    """Test health overview endpoint returns 401 for unauthenticated user."""
    response = await client.get("/api/health/overview")

    assert response.status_code == 401
