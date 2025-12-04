"""
Tests for error monitoring endpoints.
"""


import httpx
import pytest


@pytest.mark.asyncio
async def test_errors_last_success_admin(
    client, mock_admin_session, fake_internal_api
):
    """Test errors/last endpoint returns data for admin."""
    mock_errors_data = {
        "errors": [
            {
                "time": "2025-11-09T12:00:00Z",
                "error_type": "HTTPException",
                "component": "verification.commands",
                "message": "RSI profile not found",
                "traceback": None,
            }
        ]
    }

    fake_internal_api._last_errors_override = mock_errors_data

    response = await client.get(
        "/api/errors/last", cookies={"session": mock_admin_session}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["errors"]) == 1
    assert data["errors"][0]["error_type"] == "HTTPException"
    assert data["errors"][0]["component"] == "verification.commands"


@pytest.mark.asyncio
async def test_errors_last_empty(client, mock_admin_session, fake_internal_api):
    """Test errors/last endpoint handles no errors."""
    mock_errors_data = {"errors": []}

    fake_internal_api._last_errors_override = mock_errors_data

    response = await client.get(
        "/api/errors/last", cookies={"session": mock_admin_session}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["errors"]) == 0


@pytest.mark.asyncio
async def test_errors_last_with_limit(client, mock_admin_session, fake_internal_api):
    """Test errors/last endpoint respects limit parameter."""
    mock_errors_data = {
        "errors": [
            {
                "time": "2025-11-09T12:00:00Z",
                "error_type": "Error1",
                "component": "component1",
                "message": "message1",
                "traceback": None,
            },
            {
                "time": "2025-11-09T11:00:00Z",
                "error_type": "Error2",
                "component": "component2",
                "message": "message2",
                "traceback": None,
            },
        ]
    }

    fake_internal_api._last_errors_override = mock_errors_data

    response = await client.get(
        "/api/errors/last?limit=2", cookies={"session": mock_admin_session}
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["errors"]) == 2


@pytest.mark.asyncio
async def test_errors_last_unauthorized(client):
    """Test errors/last endpoint returns 401 without session."""
    response = await client.get("/api/errors/last")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_errors_last_forbidden_moderator(client, mock_moderator_session):
    """Test errors/last endpoint returns 403 for moderator."""
    response = await client.get(
        "/api/errors/last", cookies={"session": mock_moderator_session}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_errors_last_forbidden_unauthorized(client, mock_unauthorized_session):
    """Test errors/last endpoint returns 403 for unauthorized user."""
    response = await client.get(
        "/api/errors/last", cookies={"session": mock_unauthorized_session}
    )
    assert response.status_code == 400  # User has no authorized guilds


@pytest.mark.asyncio
async def test_errors_last_internal_error(
    client, mock_admin_session, fake_internal_api
):
    """Test errors/last endpoint handles internal API errors."""
    fake_internal_api._last_errors_override = httpx.RequestError(
        "Internal API unavailable",
        request=httpx.Request("GET", "http://internal"),
    )

    response = await client.get(
        "/api/errors/last", cookies={"session": mock_admin_session}
    )

    assert response.status_code == 503
    assert "Failed to fetch error logs" in response.json()["detail"]


@pytest.mark.asyncio
async def test_errors_last_http_status_error(
    client, mock_admin_session, fake_internal_api
):
    """Internal API HTTP errors should propagate status codes and detail."""
    response_obj = httpx.Response(
        404,
        request=httpx.Request("GET", "http://internal"),
        content=b'{"detail": "not found"}',
    )

    fake_internal_api._last_errors_override = httpx.HTTPStatusError(
        "not found",
        request=response_obj.request,
        response=response_obj,
    )

    response = await client.get(
        "/api/errors/last",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "not found"
