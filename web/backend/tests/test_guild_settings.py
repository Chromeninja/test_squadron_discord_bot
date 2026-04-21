"""Tests for guild settings and member endpoints."""

import json

import httpx
import pytest
from core.security import create_session_token_async
from httpx import AsyncClient

from services.db.database import Database

pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_get_bot_role_settings_defaults(
    client: AsyncClient, mock_admin_session: str
):
    """When no settings exist, all role arrays should be empty."""
    # Use guild ID 888 which has no seeded data
    # First need to create a session for guild 888
    session_888 = await create_session_token_async(
        {
            "user_id": "246604397155581954",
            "username": "TestAdmin",
            "discriminator": "0001",
            "avatar": None,
            "active_guild_id": "888",
            "authorized_guilds": {
                "888": {
                    "guild_id": "888",
                    "role_level": "bot_admin",
                    "source": "bot_owner",
                },
            },
        }
    )

    response = await client.get(
        "/api/guilds/888/settings/bot-roles",
        cookies={"session": session_888},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["bot_admins"] == []
    assert data["event_coordinators"] == []
    assert data["moderators"] == []
    assert data["main_role"] == []
    assert data["affiliate_role"] == []
    assert data["nonmember_role"] == []


@pytest.mark.asyncio
async def test_put_bot_role_settings_persists_values(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """PUT should normalize and persist role IDs for all categories."""
    # Use strings to preserve 64-bit Discord snowflake precision
    # Include 999111222 (the admin's current role) so validation passes on follow-up GET
    payload = {
        "bot_admins": ["999111222", "5", "5", "2"],
        "event_coordinators": ["21", "20", "21"],
        "moderators": ["8"],
        "main_role": ["10"],
        "affiliate_role": ["11", "12"],
        "nonmember_role": ["13"],
    }

    response = await client.put(
        "/api/guilds/123/settings/bot-roles",
        json=payload,
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == 200

    data = response.json()
    # Response should be sorted string role IDs
    assert data["bot_admins"] == ["2", "5", "999111222"]
    assert data["event_coordinators"] == ["20", "21"]
    assert data["moderators"] == ["8"]
    assert data["main_role"] == ["10"]
    assert data["affiliate_role"] == ["11", "12"]
    assert data["nonmember_role"] == ["13"]

    # Subsequent GET should match persisted data
    follow_up = await client.get(
        "/api/guilds/123/settings/bot-roles",
        cookies={"session": mock_admin_session},
    )
    assert follow_up.status_code == 200
    persisted = follow_up.json()
    assert persisted == data

    # Ensure bot was notified about the change
    assert fake_internal_api.refresh_calls
    assert fake_internal_api.refresh_calls[0]["guild_id"] == 123
    assert fake_internal_api.refresh_calls[0]["source"] == "bot_roles"


@pytest.mark.asyncio
async def test_put_bot_role_settings_updates_version_marker(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    payload = {
        "bot_admins": ["5"],
        "event_coordinators": ["6"],
        "moderators": ["7"],
        "main_role": ["10"],
        "affiliate_role": [],
        "nonmember_role": [],
    }

    response = await client.put(
        "/api/guilds/123/settings/bot-roles",
        json=payload,
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == 200

    async with Database.get_connection() as db:
        cursor = await db.execute(
            """
            SELECT value FROM guild_settings
            WHERE guild_id = ? AND key = ?
            """,
            (123, "meta.settings_version"),
        )
        row = await cursor.fetchone()

    assert row is not None
    serialized = row[0]
    payload = json.loads(serialized)
    assert payload["source"] == "bot_roles"
    assert "version" in payload


@pytest.mark.asyncio
async def test_get_guild_config_includes_default_event_settings(
    client: AsyncClient, mock_admin_session: str
) -> None:
    """Guild config should expose default event module settings."""
    response = await client.get(
        "/api/guilds/123/config",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["events"] == {
        "enabled": True,
        "default_native_sync": True,
        "default_announcement_channel_id": None,
        "default_voice_channel_id": None,
    }


@pytest.mark.asyncio
async def test_patch_guild_config_persists_event_settings(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
) -> None:
    """Guild config PATCH should persist event module settings."""
    response = await client.patch(
        "/api/guilds/123/config",
        json={
            "events": {
                "enabled": False,
                "default_native_sync": False,
                "default_announcement_channel_id": "1183902241694949386",
                "default_voice_channel_id": "1182812153271558255",
            }
        },
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["events"] == {
        "enabled": False,
        "default_native_sync": False,
        "default_announcement_channel_id": "1183902241694949386",
        "default_voice_channel_id": "1182812153271558255",
    }

    follow_up = await client.get(
        "/api/guilds/123/config",
        cookies={"session": mock_admin_session},
    )
    assert follow_up.status_code == 200
    assert follow_up.json()["data"]["events"] == data["events"]

    assert fake_internal_api.refresh_calls
    assert fake_internal_api.refresh_calls[-1]["source"] == "guild_config_patch"


@pytest.mark.asyncio
async def test_get_voice_selectable_roles_defaults(
    client: AsyncClient, mock_admin_session: str
):
    response = await client.get(
        "/api/guilds/123/settings/voice/selectable-roles",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["selectable_roles"] == []


@pytest.mark.asyncio
async def test_put_voice_selectable_roles_persists_values(
    client: AsyncClient, mock_admin_session: str
):
    # Use strings to preserve 64-bit Discord snowflake precision
    payload = {"selectable_roles": ["9", "2", "9", "5"]}

    response = await client.put(
        "/api/guilds/123/settings/voice/selectable-roles",
        json=payload,
        cookies={"session": mock_admin_session},
    )
    assert response.status_code == 200

    data = response.json()
    # Response should be sorted, deduplicated string role IDs
    assert data["selectable_roles"] == ["2", "5", "9"]

    follow_up = await client.get(
        "/api/guilds/123/settings/voice/selectable-roles",
        cookies={"session": mock_admin_session},
    )
    assert follow_up.status_code == 200
    assert follow_up.json() == data


@pytest.mark.asyncio
async def test_get_discord_roles_proxies_internal_api(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api,
):
    """Ensure the discord roles endpoint returns data from the internal API."""
    fake_internal_api.roles_by_guild[123] = [
        {"id": 10, "name": "Captain", "color": 0xFF0000},
        {"id": 11, "name": "Officer", "color": 0x00FF00},
    ]

    response = await client.get(
        "/api/guilds/123/roles/discord",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["roles"]) == 2
    assert data["roles"][0]["name"] == "Captain"


@pytest.mark.asyncio
async def test_get_discord_roles_rejects_mismatched_guild(
    client: AsyncClient, mock_admin_session: str
):
    """Requesting a non-active guild should be forbidden."""
    response = await client.get(
        "/api/guilds/999/roles/discord",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_discord_scheduled_events_proxies_internal_api(
    client: AsyncClient,
    mock_event_coordinator_session: str,
) -> None:
    """Scheduled events endpoint should return DB-backed managed events."""
    await Database.create_managed_event(
        guild_id=123,
        payload={
            "name": "Fleet Night",
            "description": "Weekly operation",
            "announcement_message": "Weekly operation",
            "scheduled_start_time": "2026-04-09T20:00:00+00:00",
            "scheduled_end_time": "2026-04-09T22:00:00+00:00",
            "entity_type": "voice",
            "channel_id": "1182812153271558255",
            "location": None,
            "announcement_channel_id": "1182812153271558256",
            "signup_role_ids": [],
        },
        created_by_user_id="444333222",
        created_by_name="TestEventCoordinator",
    )

    response = await client.get(
        "/api/guilds/123/events/scheduled",
        cookies={"session": mock_event_coordinator_session},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["events"]) == 1
    assert data["events"][0]["name"] == "Fleet Night"
    assert data["events"][0]["entity_type"] == "voice"
    assert data["events"][0]["source_of_truth"] == "db"


@pytest.mark.asyncio
async def test_get_discord_scheduled_events_requires_event_coordinator(
    client: AsyncClient,
    mock_staff_session: str,
) -> None:
    """Staff users should not be allowed to access scheduled events."""
    response = await client.get(
        "/api/guilds/123/events/scheduled",
        cookies={"session": mock_staff_session},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_discord_scheduled_event_proxies_internal_api(
    client: AsyncClient,
    mock_event_coordinator_session: str,
    fake_internal_api,
) -> None:
    """Scheduled event creation should proxy through the internal API."""
    response = await client.post(
        "/api/guilds/123/events/scheduled",
        json={
            "name": "Ops Night",
            "description": "Create route test",
            "scheduled_start_time": "2026-04-09T20:00:00+00:00",
            "scheduled_end_time": "2026-04-09T22:00:00+00:00",
            "entity_type": "voice",
            "location": None,
            "channel_id": "1182812153271558255",
        },
        cookies={"session": mock_event_coordinator_session},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["event"]["name"] == "Ops Night"
    assert fake_internal_api.scheduled_events_by_guild[123][-1]["name"] == "Ops Night"


@pytest.mark.asyncio
async def test_create_discord_scheduled_event_forwards_announcement_message(
    client: AsyncClient,
    mock_event_coordinator_session: str,
    fake_internal_api,
) -> None:
    """Create route should forward announcement_message to internal API."""
    captured_payload: dict[str, object] = {}

    async def create_event(guild_id: int, payload: dict) -> dict:
        del guild_id
        captured_payload.update(payload)
        return {
            "id": "900000000000000001",
            "name": payload.get("name", "Ops Night"),
            "description": payload.get("description"),
            "scheduled_start_time": payload.get("scheduled_start_time"),
            "scheduled_end_time": payload.get("scheduled_end_time"),
            "status": "scheduled",
            "entity_type": payload.get("entity_type", "voice"),
            "channel_id": payload.get("channel_id"),
            "channel_name": "Mock Event Channel",
            "location": payload.get("location"),
            "user_count": 0,
            "creator_id": "444333222",
            "creator_name": "TestEventCoordinator",
            "image_url": None,
        }

    fake_internal_api.create_guild_scheduled_event = create_event

    response = await client.post(
        "/api/guilds/123/events/scheduled",
        json={
            "name": "Ops Night",
            "description": "Create route test",
            "announcement_message": "Custom announcement body",
            "scheduled_start_time": "2026-04-09T20:00:00+00:00",
            "scheduled_end_time": "2026-04-09T22:00:00+00:00",
            "entity_type": "voice",
            "location": None,
            "channel_id": "1182812153271558255",
        },
        cookies={"session": mock_event_coordinator_session},
    )

    assert response.status_code == 200
    assert captured_payload["announcement_message"] == "Custom announcement body"
    assert isinstance(captured_payload.get("created_by_name"), str)


@pytest.mark.asyncio
async def test_update_discord_scheduled_event_proxies_internal_api(
    client: AsyncClient,
    mock_event_coordinator_session: str,
    fake_internal_api,
) -> None:
    """Scheduled event updates should update DB and then project to internal API."""
    created_response = await client.post(
        "/api/guilds/123/events/scheduled",
        json={
            "name": "Ops Night",
            "description": "Initial description",
            "scheduled_start_time": "2026-04-09T20:00:00+00:00",
            "scheduled_end_time": "2026-04-09T22:00:00+00:00",
            "entity_type": "voice",
            "location": None,
            "channel_id": "1182812153271558255",
        },
        cookies={"session": mock_event_coordinator_session},
    )
    assert created_response.status_code == 200
    local_event_id = created_response.json()["event"]["id"]

    response = await client.put(
        f"/api/guilds/123/events/scheduled/{local_event_id}",
        json={
            "name": "Ops Night Updated",
            "description": "Updated description",
            "scheduled_start_time": "2026-04-10T20:00:00+00:00",
            "scheduled_end_time": "2026-04-10T22:00:00+00:00",
            "entity_type": "voice",
            "location": None,
            "channel_id": "1182812153271558255",
        },
        cookies={"session": mock_event_coordinator_session},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["event"]["name"] == "Ops Night Updated"
    assert data["event"]["location"] is None
    assert data["event"]["source_of_truth"] == "db"
    assert fake_internal_api.scheduled_events_by_guild[123][0]["entity_type"] == "voice"


@pytest.mark.asyncio
async def test_manual_event_sync_reconcile_uses_db_wins_projection(
    client: AsyncClient,
    mock_event_coordinator_session: str,
    fake_internal_api,
) -> None:
    """Manual reconcile should run pull+push and return DB-backed event inventory."""
    create_response = await client.post(
        "/api/guilds/123/events/scheduled",
        json={
            "name": "Sync Test",
            "description": "Initial",
            "scheduled_start_time": "2026-04-11T20:00:00+00:00",
            "scheduled_end_time": "2026-04-11T22:00:00+00:00",
            "entity_type": "voice",
            "location": None,
            "channel_id": "1182812153271558255",
        },
        cookies={"session": mock_event_coordinator_session},
    )
    assert create_response.status_code == 200

    sync_response = await client.post(
        "/api/guilds/123/events/scheduled/sync",
        json={"direction": "reconcile"},
        cookies={"session": mock_event_coordinator_session},
    )

    assert sync_response.status_code == 200
    data = sync_response.json()
    assert data["success"] is True
    assert data["direction"] == "reconcile"
    assert data["processed"] >= 1
    assert len(data["events"]) >= 1


@pytest.mark.asyncio
async def test_manual_event_sync_reconcile_persists_user_count_from_discord(
    client: AsyncClient,
    mock_event_coordinator_session: str,
    fake_internal_api,
) -> None:
    """Manual reconcile should persist Discord interested counts into DB-backed reads."""
    create_response = await client.post(
        "/api/guilds/123/events/scheduled",
        json={
            "name": "Interest Sync Test",
            "description": "Initial",
            "scheduled_start_time": "2026-04-11T20:00:00+00:00",
            "scheduled_end_time": "2026-04-11T22:00:00+00:00",
            "entity_type": "voice",
            "location": None,
            "channel_id": "1182812153271558255",
        },
        cookies={"session": mock_event_coordinator_session},
    )
    assert create_response.status_code == 200

    fake_internal_api.scheduled_events_by_guild[123][0]["user_count"] = 27

    sync_response = await client.post(
        "/api/guilds/123/events/scheduled/sync",
        json={"direction": "reconcile"},
        cookies={"session": mock_event_coordinator_session},
    )

    assert sync_response.status_code == 200
    sync_data = sync_response.json()
    assert sync_data["events"][0]["user_count"] == 27

    list_response = await client.get(
        "/api/guilds/123/events/scheduled",
        cookies={"session": mock_event_coordinator_session},
    )

    assert list_response.status_code == 200
    list_data = list_response.json()
    assert list_data["events"][0]["user_count"] == 27


@pytest.mark.asyncio
async def test_create_discord_scheduled_event_rejects_external_entity_type(
    client: AsyncClient,
    mock_event_coordinator_session: str,
) -> None:
    """Scheduled event create should reject non-voice entity types."""
    response = await client.post(
        "/api/guilds/123/events/scheduled",
        json={
            "name": "External Test",
            "description": "Should fail validation",
            "scheduled_start_time": "2026-04-10T20:00:00+00:00",
            "scheduled_end_time": "2026-04-10T21:00:00+00:00",
            "entity_type": "external",
            "location": "Spectrum",
            "channel_id": None,
        },
        cookies={"session": mock_event_coordinator_session},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_guild_members_proxies_internal_api(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api,
):
    """Members endpoint should return paginated data from internal API."""
    fake_internal_api.members_by_guild[123] = [
        {
            "user_id": 111,
            "username": "Alpha",
            "discriminator": "0001",
            "global_name": "Alpha",
            "roles": [
                {"id": 5, "name": "Pilot", "color": 0x123456},
            ],
        }
    ]

    response = await client.get(
        "/api/guilds/123/members?page=1&page_size=50",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["total"] == 1
    assert data["members"][0]["user_id"] == 111
    assert data["members"][0]["roles"][0]["name"] == "Pilot"

    @pytest.mark.asyncio
    async def test_guild_config_read_only_uses_shared_loader(
        monkeypatch, tmp_path, client: AsyncClient, mock_admin_session: str
    ):
        custom_config = tmp_path / "custom-config.yaml"
        custom_config.write_text(
            """
    rsi:
      user_agent: CUSTOM-UA
    voice_debug_logging_enabled: true
    """,
            encoding="utf-8",
        )

        # Ensure ConfigLoader consumes the override before client fixture initializes
        monkeypatch.setenv("CONFIG_PATH", str(custom_config))

        response = await client.get(
            "/api/guilds/123/config", cookies={"session": mock_admin_session}
        )

        assert response.status_code == 200
        ro = response.json()["data"]["read_only"]
        assert ro["rsi"]["user_agent"] == "CUSTOM-UA"
        assert ro["voice_debug_logging_enabled"] is True


@pytest.mark.asyncio
async def test_list_guild_members_forbidden_without_matching_active_guild(
    client: AsyncClient,
):
    """Users cannot query a guild different from the selected active guild."""
    mismatch_session = await create_session_token_async(
        {
            "user_id": "246604397155581954",
            "username": "TestAdmin",
            "discriminator": "0001",
            "avatar": None,
            "is_admin": True,
            "is_moderator": False,
            "active_guild_id": "999",
            "authorized_guilds": {
                "999": {
                    "guild_id": "999",
                    "role_level": "bot_admin",
                    "source": "bot_admin_role",
                },
                "123": {
                    "guild_id": "123",
                    "role_level": "bot_admin",
                    "source": "bot_admin_role",
                },
            },
        }
    )

    response = await client.get(
        "/api/guilds/123/members",
        cookies={"session": mismatch_session},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_guild_member_detail_success(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api,
):
    """Single member endpoint returns normalized payload."""
    fake_internal_api.member_data[(123, 555)] = {
        "user_id": 555,
        "username": "Bravo",
        "discriminator": "1234",
        "global_name": "Bravo",
        "avatar_url": None,
        "roles": [],
    }

    response = await client.get(
        "/api/guilds/123/members/555",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["member"]["user_id"] == 555
    assert data["member"]["username"] == "Bravo"


@pytest.mark.asyncio
async def test_get_guild_member_detail_http_status_error(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api,
):
    """HTTP errors from the internal API should propagate status and detail."""
    error_response = httpx.Response(
        404,
        request=httpx.Request("GET", "http://internal"),
        content=json.dumps({"detail": "Member not found"}).encode(),
    )

    # Override get_guild_member to raise an exception ONLY for user 999
    # For the admin user (246604397155581954), return normal data for role validation
    original_get_guild_member = fake_internal_api.get_guild_member

    async def selective_raise_error(guild_id, user_id):
        if user_id == 999:
            raise httpx.HTTPStatusError(
                "not found",
                request=error_response.request,
                response=error_response,
            )
        # For role validation of admin user, return normal member data
        return await original_get_guild_member(guild_id, user_id)

    fake_internal_api.get_guild_member = selective_raise_error

    response = await client.get(
        "/api/guilds/123/members/999",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Member not found"


@pytest.mark.asyncio
async def test_get_guild_config_metrics_defaults(
    client: AsyncClient, mock_admin_session: str
):
    """Guild config includes metrics settings defaults."""
    response = await client.get(
        "/api/guilds/123/config",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["metrics"]["excluded_channel_ids"] == []


@pytest.mark.asyncio
async def test_patch_guild_config_metrics_persists(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """PATCH /config persists and normalizes metrics excluded channel IDs."""
    payload = {
        "metrics": {
            "excluded_channel_ids": ["200", "100", "200", "invalid"],
        }
    }

    response = await client.patch(
        "/api/guilds/123/config",
        json=payload,
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["metrics"]["excluded_channel_ids"] == ["100", "200"]

    follow_up = await client.get(
        "/api/guilds/123/config",
        cookies={"session": mock_admin_session},
    )
    assert follow_up.status_code == 200
    assert follow_up.json()["data"]["metrics"]["excluded_channel_ids"] == ["100", "200"]

    assert fake_internal_api.refresh_calls


@pytest.mark.asyncio
async def test_get_guild_config_metrics_threshold_defaults(
    client: AsyncClient, mock_admin_session: str
):
    """Guild config includes default activity threshold settings."""
    response = await client.get(
        "/api/guilds/123/config",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()["data"]["metrics"]
    assert data["min_voice_minutes"] == 15
    assert data["min_game_minutes"] == 15
    assert data["min_messages"] == 5


@pytest.mark.asyncio
async def test_patch_guild_config_metrics_thresholds_persists(
    client: AsyncClient, mock_admin_session: str, fake_internal_api
):
    """PATCH /config persists activity threshold settings."""
    payload = {
        "metrics": {
            "excluded_channel_ids": [],
            "min_voice_minutes": 30,
            "min_game_minutes": 20,
            "min_messages": 10,
        }
    }

    response = await client.patch(
        "/api/guilds/123/config",
        json=payload,
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    body = response.json()["data"]["metrics"]
    assert body["min_voice_minutes"] == 30
    assert body["min_game_minutes"] == 20
    assert body["min_messages"] == 10

    # Confirm persisted on subsequent read
    follow_up = await client.get(
        "/api/guilds/123/config",
        cookies={"session": mock_admin_session},
    )
    assert follow_up.status_code == 200
    data = follow_up.json()["data"]["metrics"]
    assert data["min_voice_minutes"] == 30
    assert data["min_game_minutes"] == 20
    assert data["min_messages"] == 10
