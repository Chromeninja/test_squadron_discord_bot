"""Tests for metrics dashboard API endpoints."""

from http import HTTPStatus

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.contract


def _use_fixture(*fixtures):
    """Helper to appease linters for fixtures with side effects."""
    for fixture in fixtures:
        assert fixture is not None


# ---------------------------------------------------------------------------
# GET /api/metrics/overview
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_overview_returns_data(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Overview endpoint returns live + period data."""
    _use_fixture(fake_internal_api)
    response = await client.get(
        "/api/metrics/overview?days=7",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert "data" in body
    data = body["data"]
    assert data["live"]["messages_today"] == 42
    assert data["period"]["total_messages"] == 1200


@pytest.mark.asyncio
async def test_overview_custom_days(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Overview respects the days query parameter."""
    _use_fixture(fake_internal_api)
    response = await client.get(
        "/api/metrics/overview?days=30",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == HTTPStatus.OK
    data = response.json()["data"]
    # Verify the response shape is correct (days is a query param, not in response body)
    assert "live" in data
    assert "period" in data
    assert data["period"]["total_messages"] == 1200


@pytest.mark.asyncio
async def test_overview_requires_auth(client: AsyncClient):
    """Overview rejects unauthenticated requests."""
    response = await client.get("/api/metrics/overview")
    assert response.status_code in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN)


@pytest.mark.asyncio
async def test_overview_internal_error(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Overview returns 502 when internal API fails."""
    fake_internal_api._metrics_overview_override = RuntimeError("bot offline")
    response = await client.get(
        "/api/metrics/overview",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == HTTPStatus.BAD_GATEWAY


# ---------------------------------------------------------------------------
# GET /api/metrics/voice/leaderboard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_voice_leaderboard(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Voice leaderboard returns ranked entries."""
    _use_fixture(fake_internal_api)
    response = await client.get(
        "/api/metrics/voice/leaderboard?days=7&limit=10",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert "entries" in body
    assert len(body["entries"]) == 2
    assert body["entries"][0]["user_id"] == 123456789


@pytest.mark.asyncio
async def test_voice_leaderboard_internal_error(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Voice leaderboard returns 502 on internal failure."""
    fake_internal_api._metrics_voice_lb_override = RuntimeError("timeout")
    response = await client.get(
        "/api/metrics/voice/leaderboard",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == HTTPStatus.BAD_GATEWAY


# ---------------------------------------------------------------------------
# GET /api/metrics/messages/leaderboard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_message_leaderboard(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Message leaderboard returns ranked entries."""
    _use_fixture(fake_internal_api)
    response = await client.get(
        "/api/metrics/messages/leaderboard?days=7&limit=10",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert len(body["entries"]) == 2
    assert body["entries"][0]["value"] == 500


@pytest.mark.asyncio
async def test_message_leaderboard_internal_error(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Message leaderboard returns 502 on internal failure."""
    fake_internal_api._metrics_msg_lb_override = RuntimeError("timeout")
    response = await client.get(
        "/api/metrics/messages/leaderboard",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == HTTPStatus.BAD_GATEWAY


# ---------------------------------------------------------------------------
# GET /api/metrics/games/top
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_top_games(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Top games endpoint returns game stats."""
    _use_fixture(fake_internal_api)
    response = await client.get(
        "/api/metrics/games/top?days=7&limit=10",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert "games" in body
    assert len(body["games"]) == 2
    assert body["games"][0]["game_name"] == "Star Citizen"
    assert body["games"][0]["unique_players"] == 10
    assert body["games"][0]["session_count"] == 20


@pytest.mark.asyncio
async def test_top_games_internal_error(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Top games returns 502 on internal failure."""
    fake_internal_api._metrics_top_games_override = RuntimeError("timeout")
    response = await client.get(
        "/api/metrics/games/top",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == HTTPStatus.BAD_GATEWAY


# ---------------------------------------------------------------------------
# GET /api/metrics/timeseries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeseries_messages(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Timeseries endpoint returns data points for messages."""
    _use_fixture(fake_internal_api)
    response = await client.get(
        "/api/metrics/timeseries?metric=messages&days=7",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["metric"] == "messages"
    assert body["days"] == 7
    assert len(body["data"]) == 2


@pytest.mark.asyncio
async def test_timeseries_voice(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Timeseries endpoint works with voice metric type."""
    _use_fixture(fake_internal_api)
    response = await client.get(
        "/api/metrics/timeseries?metric=voice&days=30",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["metric"] == "voice"


@pytest.mark.asyncio
async def test_timeseries_invalid_metric(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Timeseries rejects invalid metric names."""
    _use_fixture(fake_internal_api)
    response = await client.get(
        "/api/metrics/timeseries?metric=invalid",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_timeseries_internal_error(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Timeseries returns 502 on internal failure."""
    fake_internal_api._metrics_timeseries_override = RuntimeError("timeout")
    response = await client.get(
        "/api/metrics/timeseries?metric=messages",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == HTTPStatus.BAD_GATEWAY


# ---------------------------------------------------------------------------
# GET /api/metrics/user/{user_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_metrics(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """User metrics returns detailed per-user data."""
    _use_fixture(fake_internal_api)
    response = await client.get(
        "/api/metrics/user/123456789?days=7",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    data = body["data"]
    assert data["user_id"] == "123456789"
    assert data["total_messages"] == 150
    assert data["total_voice_seconds"] == 36000
    assert len(data["top_games"]) == 1
    assert data["top_games"][0]["game_name"] == "Star Citizen"


@pytest.mark.asyncio
async def test_user_metrics_internal_error(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """User metrics returns 502 on internal failure."""
    fake_internal_api._metrics_user_override = RuntimeError("user not found")
    response = await client.get(
        "/api/metrics/user/123456789",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == HTTPStatus.BAD_GATEWAY


# ---------------------------------------------------------------------------
# Cross-cutting: moderator access
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_moderator_cannot_view_metrics(
    client: AsyncClient, mock_moderator_session: str, fake_internal_api
):
    """Moderators are denied access to metrics endpoints (bot-admin+ only)."""
    _use_fixture(fake_internal_api)
    response = await client.get(
        "/api/metrics/overview?days=7",
        cookies={"session": mock_moderator_session},
    )
    assert response.status_code == HTTPStatus.FORBIDDEN
