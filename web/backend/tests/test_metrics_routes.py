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
async def test_dashboard_metrics_bundle_returns_data(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api,
) -> None:
    """Bundled metrics endpoint returns normalized page data from one route."""
    captured_calls: dict[str, dict[str, object]] = {}

    async def _capture_bulk(
        guild_id: int,
        dimensions: list[str],
        tiers: list[str],
        days: int = 30,
    ) -> dict[str, dict[str, list[int]]]:
        captured_calls["bulk"] = {
            "guild_id": guild_id,
            "dimensions": dimensions,
            "tiers": tiers,
            "days": days,
        }
        return {"voice": {"regular": [123456789]}}

    async def _capture_overview(
        guild_id: int,
        days: int = 7,
        user_ids: list[int] | None = None,
    ) -> dict:
        captured_calls["overview"] = {
            "guild_id": guild_id,
            "days": days,
            "user_ids": user_ids,
        }
        return {
            "live": {
                "messages_today": 42,
                "active_voice_users": 3,
                "top_game": "Star Citizen",
                "active_game_sessions": 5,
            },
            "period": {
                "total_messages": 1200,
                "unique_messagers": 25,
                "avg_messages_per_user": 48.0,
                "total_voice_seconds": 360000,
                "unique_voice_users": 18,
                "avg_voice_per_user": 20000,
                "unique_users": 30,
                "top_games": [],
            },
        }

    async def _capture_voice(
        guild_id: int,
        days: int = 7,
        limit: int = 10,
        user_ids: list[int] | None = None,
    ) -> dict:
        captured_calls["voice"] = {
            "guild_id": guild_id,
            "days": days,
            "limit": limit,
            "user_ids": user_ids,
        }
        return {
            "entries": [{"user_id": 123456789, "value": 7200.0, "username": "PilotOne"}]
        }

    async def _capture_messages(
        guild_id: int,
        days: int = 7,
        limit: int = 10,
        user_ids: list[int] | None = None,
    ) -> dict:
        captured_calls["messages"] = {
            "guild_id": guild_id,
            "days": days,
            "limit": limit,
            "user_ids": user_ids,
        }
        return {
            "entries": [{"user_id": 123456789, "value": 500, "username": "PilotOne"}]
        }

    async def _capture_top_games(
        guild_id: int,
        days: int = 7,
        limit: int = 10,
        user_ids: list[int] | None = None,
    ) -> dict:
        captured_calls["games"] = {
            "guild_id": guild_id,
            "days": days,
            "limit": limit,
            "user_ids": user_ids,
        }
        return {
            "games": [
                {
                    "game_name": "Star Citizen",
                    "total_seconds": 72000,
                    "session_count": 20,
                    "avg_seconds": 3600,
                    "unique_players": 10,
                }
            ]
        }

    async def _capture_timeseries(
        guild_id: int,
        metric: str = "messages",
        days: int = 7,
        user_ids: list[int] | None = None,
    ) -> dict:
        captured_calls[f"timeseries:{metric}"] = {
            "guild_id": guild_id,
            "days": days,
            "user_ids": user_ids,
        }
        return {
            "metric": metric,
            "days": days,
            "data": [
                {"timestamp": 1735689600, "value": 10, "unique_users": 2},
            ],
        }

    async def _capture_groups(
        guild_id: int,
        days: int = 7,
        user_ids: list[int] | None = None,
    ) -> dict:
        captured_calls["groups"] = {
            "guild_id": guild_id,
            "days": days,
            "user_ids": user_ids,
        }
        tier_counts = {
            "hardcore": 2,
            "regular": 5,
            "casual": 8,
            "reserve": 10,
            "inactive": 25,
        }
        return {
            "all": tier_counts,
            "voice": tier_counts,
            "chat": tier_counts,
            "game": tier_counts,
        }

    fake_internal_api.get_activity_group_members_bulk = _capture_bulk
    fake_internal_api.get_metrics_overview = _capture_overview
    fake_internal_api.get_metrics_voice_leaderboard = _capture_voice
    fake_internal_api.get_metrics_message_leaderboard = _capture_messages
    fake_internal_api.get_metrics_top_games = _capture_top_games
    fake_internal_api.get_metrics_timeseries = _capture_timeseries
    fake_internal_api.get_activity_groups = _capture_groups

    response = await client.get(
        "/api/metrics/dashboard?days=30&dimension=voice&tier=regular",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["overview"]["period"]["total_messages"] == 1200
    assert data["voice_leaderboard"][0]["user_id"] == "123456789"
    assert data["voice_leaderboard"][0]["total_seconds"] == 7200
    assert data["message_leaderboard"][0]["total_messages"] == 500
    assert data["top_games"][0]["game_name"] == "Star Citizen"
    assert data["message_timeseries"][0]["timestamp"] == 1735689600
    assert data["activity_counts"]["all"]["regular"] == 5
    assert captured_calls["bulk"] == {
        "guild_id": 123,
        "dimensions": ["voice"],
        "tiers": ["regular"],
        "days": 30,
    }
    for key in (
        "overview",
        "voice",
        "messages",
        "games",
        "timeseries:messages",
        "timeseries:voice",
        "groups",
    ):
        call = captured_calls[key]
        assert call["guild_id"] == 123
        assert call["days"] == 30
        assert call["user_ids"] == [123456789]


@pytest.mark.asyncio
async def test_dashboard_metrics_bundle_internal_error(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api,
) -> None:
    """Bundled metrics endpoint returns 502 if one internal call fails."""
    _use_fixture(fake_internal_api)
    fake_internal_api._metrics_top_games_override = RuntimeError("timeout")

    response = await client.get(
        "/api/metrics/dashboard?days=7",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == HTTPStatus.BAD_GATEWAY
    assert response.json()["detail"] == "Bundled dashboard metrics unavailable"


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
    assert body["entries"][0]["user_id"] == "123456789"


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
    assert body["entries"][0]["total_messages"] == 500


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


@pytest.mark.asyncio
async def test_game_metrics_detail(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Game detail endpoint returns per-game overview and top players."""
    _use_fixture(fake_internal_api)
    response = await client.get(
        "/api/metrics/games/detail?game_name=Star%20Citizen&days=7&limit=5",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert "data" in body
    assert body["data"]["game_name"] == "Star Citizen"
    assert body["data"]["unique_players"] == 7
    assert len(body["data"]["top_players"]) == 2
    assert body["data"]["top_players"][0]["user_id"] == "123456789"


@pytest.mark.asyncio
async def test_game_metrics_detail_internal_error(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Game detail endpoint returns 502 on internal failure."""
    fake_internal_api._metrics_game_override = RuntimeError("timeout")
    response = await client.get(
        "/api/metrics/games/detail?game_name=Star%20Citizen",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == HTTPStatus.BAD_GATEWAY
    assert response.json()["detail"] == "Game metrics unavailable"


@pytest.mark.asyncio
async def test_game_metrics_detail_filter_too_broad(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api,
    monkeypatch: pytest.MonkeyPatch,
):
    """Game detail endpoint rejects oversized resolved user filters."""
    _use_fixture(fake_internal_api)

    async def _resolve_many(*_args, **_kwargs) -> list[int]:
        return list(range(1, 1005))

    monkeypatch.setattr(
        "routes.metrics._resolve_activity_filter",
        _resolve_many,
    )

    response = await client.get(
        "/api/metrics/games/detail?game_name=Star%20Citizen&days=7&limit=5"
        "&dimension=all&tier=regular",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "too many users" in response.json()["detail"].lower()


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
    assert data["combined_tier"] == "inactive"
    assert data["voice_tier"] == "inactive"
    assert data["chat_tier"] == "inactive"
    assert data["game_tier"] == "inactive"


@pytest.mark.asyncio
async def test_user_metrics_coerces_integer_user_id(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """User metrics route coerces int user_id payloads to string."""
    _use_fixture(fake_internal_api)
    fake_internal_api._metrics_user_override = {
        "user_id": 134465907190661120,
        "total_messages": 42,
        "total_voice_seconds": 3600,
        "avg_messages_per_day": 1.4,
        "avg_voice_per_day": 120,
        "top_games": [],
        "timeseries": [],
    }

    response = await client.get(
        "/api/metrics/user/134465907190661120?days=30",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["data"]["user_id"] == "134465907190661120"


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
    body = response.json()
    assert body["detail"] == "User metrics unavailable"


@pytest.mark.asyncio
async def test_delete_user_metrics_success_audited(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api,
    monkeypatch: pytest.MonkeyPatch,
):
    """Delete metrics success path writes audit log and returns payload."""
    _use_fixture(fake_internal_api)
    calls: list[dict] = []

    async def _fake_log_admin_action(**kwargs) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(
        "routes.metrics.log_admin_action",
        _fake_log_admin_action,
    )

    response = await client.delete(
        "/api/metrics/user/123456789",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        "deleted": {
            "messages": 10,
            "voice_sessions": 3,
            "game_sessions": 2,
        }
    }
    assert len(calls) == 1
    assert calls[0]["action"] == "DELETE_USER_METRICS"
    assert calls[0]["status"] == "success"
    assert calls[0]["target_user_id"] == 123456789


@pytest.mark.asyncio
async def test_delete_user_metrics_error_audited(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api,
    monkeypatch: pytest.MonkeyPatch,
):
    """Delete metrics failure writes error audit and returns 502."""
    _use_fixture(fake_internal_api)
    fake_internal_api._metrics_delete_user_override = RuntimeError("boom")
    calls: list[dict] = []

    async def _fake_log_admin_action(**kwargs) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(
        "routes.metrics.log_admin_action",
        _fake_log_admin_action,
    )

    response = await client.delete(
        "/api/metrics/user/123456789",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == HTTPStatus.BAD_GATEWAY
    assert response.json()["detail"] == "Failed to delete user metrics"
    assert len(calls) == 1
    assert calls[0]["action"] == "DELETE_USER_METRICS"
    assert calls[0]["status"] == "error"
    assert calls[0]["target_user_id"] == 123456789


# ---------------------------------------------------------------------------
# Cross-cutting: moderator access
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_moderator_cannot_view_metrics(
    client: AsyncClient, mock_moderator_session: str, fake_internal_api
):
    """Moderators are denied access to metrics endpoints (discord-manager+ only)."""
    _use_fixture(fake_internal_api)
    response = await client.get(
        "/api/metrics/overview?days=7",
        cookies={"session": mock_moderator_session},
    )
    assert response.status_code == HTTPStatus.FORBIDDEN


@pytest.mark.asyncio
async def test_discord_manager_can_view_metrics(
    client: AsyncClient, mock_discord_manager_session: str, fake_internal_api
):
    """Discord managers can access metrics endpoints."""
    _use_fixture(fake_internal_api)
    response = await client.get(
        "/api/metrics/overview?days=7",
        cookies={"session": mock_discord_manager_session},
    )
    assert response.status_code == HTTPStatus.OK


# ---------------------------------------------------------------------------
# Activity group filters on existing routes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_overview_with_dimension_tier_filter(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Overview endpoint accepts dimension and tier query params."""
    _use_fixture(fake_internal_api)
    response = await client.get(
        "/api/metrics/overview?days=7&dimension=voice&tier=hardcore",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert "data" in body


@pytest.mark.asyncio
async def test_overview_bad_dimension_rejected(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Overview rejects invalid dimension values."""
    _use_fixture(fake_internal_api)
    response = await client.get(
        "/api/metrics/overview?days=7&dimension=invalid",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_overview_bad_tier_rejected(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Overview rejects invalid tier values."""
    _use_fixture(fake_internal_api)
    response = await client.get(
        "/api/metrics/overview?days=7&tier=diamond",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_voice_leaderboard_with_filter(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Voice leaderboard accepts dimension+tier filters."""
    _use_fixture(fake_internal_api)
    response = await client.get(
        "/api/metrics/voice/leaderboard?days=7&dimension=all&tier=regular",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == HTTPStatus.OK
    assert "entries" in response.json()


# ---------------------------------------------------------------------------
# GET /api/metrics/activity-groups
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_activity_groups_returns_counts(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Activity-groups endpoint returns tier counts per dimension."""
    _use_fixture(fake_internal_api)
    response = await client.get(
        "/api/metrics/activity-groups",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    for dim in ("all", "voice", "chat", "game"):
        assert dim in data
        for tier in ("hardcore", "regular", "casual", "reserve", "inactive"):
            assert tier in data[dim]


@pytest.mark.asyncio
async def test_activity_groups_accepts_filters(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Activity-groups endpoint accepts days + dimension/tier filters."""
    _use_fixture(fake_internal_api)
    response = await client.get(
        "/api/metrics/activity-groups?days=30&dimension=voice,chat&tier=regular",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == HTTPStatus.OK
    assert response.json()["success"] is True


@pytest.mark.asyncio
async def test_activity_groups_requires_auth(client: AsyncClient):
    """Activity-groups rejects unauthenticated requests."""
    response = await client.get("/api/metrics/activity-groups")
    assert response.status_code in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN)


# ---------------------------------------------------------------------------
# Activity filter uses bulk endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_overview_multi_dimension_filter(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Overview accepts comma-separated dimensions and resolves via bulk endpoint."""
    _use_fixture(fake_internal_api)
    response = await client.get(
        "/api/metrics/overview?days=7&dimension=voice,chat&tier=hardcore",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == HTTPStatus.OK
    assert "data" in response.json()


@pytest.mark.asyncio
async def test_filter_all_dimension_maps_to_combined(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """'all' dimension is mapped to 'combined' before calling bulk endpoint."""
    _use_fixture(fake_internal_api)
    response = await client.get(
        "/api/metrics/overview?days=7&dimension=all&tier=regular",
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == HTTPStatus.OK


@pytest.mark.asyncio
async def test_filter_returns_none_when_no_match(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """When bulk endpoint returns empty lists, filter resolves to None (unfiltered)."""

    async def _empty_bulk(
        guild_id: int, dimensions: list[str], tiers: list[str]
    ) -> dict[str, dict[str, list[int]]]:
        return {d: {t: [] for t in tiers} for d in dimensions}

    fake_internal_api.get_activity_group_members_bulk = _empty_bulk
    response = await client.get(
        "/api/metrics/overview?days=7&dimension=voice&tier=inactive",
        cookies={"session": mock_admin_session},
    )
    # Should still succeed — falls back to unfiltered
    assert response.status_code == HTTPStatus.OK


@pytest.mark.asyncio
async def test_filter_resolution_error_fails_closed(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """Filter resolution failures pass an empty user list (fail-closed)."""

    async def _raise_bulk(
        guild_id: int,
        dimensions: list[str],
        tiers: list[str],
        days: int = 30,
    ) -> dict[str, dict[str, list[int]]]:
        raise RuntimeError("bulk unavailable")

    captured_user_ids: list[int] | None = None

    async def _capture_overview(
        guild_id: int,
        days: int = 7,
        user_ids: list[int] | None = None,
    ) -> dict:
        nonlocal captured_user_ids
        captured_user_ids = user_ids
        return {
            "live": {
                "messages_today": 42,
                "active_voice_users": 3,
                "top_game": "Star Citizen",
                "active_game_sessions": 5,
            },
            "period": {
                "total_messages": 1200,
                "unique_messagers": 25,
                "avg_messages_per_user": 48.0,
                "total_voice_seconds": 360000,
                "unique_voice_users": 18,
                "avg_voice_per_user": 20000,
                "unique_users": 30,
                "top_games": [],
            },
        }

    fake_internal_api.get_activity_group_members_bulk = _raise_bulk
    fake_internal_api.get_metrics_overview = _capture_overview

    response = await client.get(
        "/api/metrics/overview?days=7&dimension=voice&tier=hardcore",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == HTTPStatus.OK
    assert captured_user_ids == []
