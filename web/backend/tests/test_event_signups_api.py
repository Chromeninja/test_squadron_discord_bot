"""API tests for event signup, role, roster, export, and messaging flows.

Covers the server-side permission and enforcement rules added for the Event
Manager expansion: regular members can access active events and signups, but
past events, rosters, exports, messaging, and event management remain gated.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

GUILD = "123"
GUILD_INT = 123


async def _make_session(user_id, role_level, source, *, is_owner=False):
    """Build a signed session cookie with fresh validation to skip live checks."""
    from core.security import create_session_token_async

    return await create_session_token_async(
        {
            "user_id": user_id,
            "username": f"User{user_id}",
            "discriminator": "0001",
            "avatar": None,
            "active_guild_id": GUILD,
            "authorized_guilds": {
                GUILD: {
                    "guild_id": GUILD,
                    "role_level": role_level,
                    "source": source,
                }
            },
            # Recent timestamp => role validation TTL skips live re-validation,
            # so the session's role_level is trusted for the test.
            "roles_validated_at": {GUILD: int(time.time())},
            "is_bot_owner": is_owner,
        }
    )


def _iso(delta_days):
    return (datetime.now(UTC) + timedelta(days=delta_days)).isoformat()


async def _create_event(name, *, start_days, end_days, status="scheduled"):
    """Insert a managed event directly and return its integer id."""
    from services.db.database import Database

    event = await Database.create_managed_event(
        guild_id=GUILD_INT,
        payload={
            "name": name,
            "scheduled_start_time": _iso(start_days),
            "scheduled_end_time": _iso(end_days),
            "entity_type": "voice",
            "channel_id": "555000111",
        },
        created_by_user_id="444333222",
        created_by_name="Coordinator",
    )
    eid = int(str(event["id"]))
    if status != "scheduled":
        async with Database.get_connection() as db:
            await db.execute(
                "UPDATE managed_events SET status = ? WHERE guild_id = ? AND id = ?",
                (status, GUILD_INT, eid),
            )
            await db.commit()
    return eid


@pytest_asyncio.fixture
async def sessions(backend_test_runtime):
    """Provide signed session cookies for each role used by the tests."""
    return {
        "user": await _make_session("700000001", "user", "guild_member"),
        "user2": await _make_session("700000002", "user", "guild_member"),
        "coordinator": await _make_session(
            "444333222", "event_coordinator", "event_coordinator_role"
        ),
        "owner": await _make_session(
            "246604397155581954", "bot_owner", "bot_owner", is_owner=True
        ),
    }


# ---------------------------------------------------------------------------
# Visibility / access
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_regular_member_sees_only_active_events(client, temp_db, sessions):
    active_id = await _create_event("ActiveOne", start_days=1, end_days=2)
    await _create_event("PastOne", start_days=-5, end_days=-4)

    resp = await client.get(
        f"/api/guilds/{GUILD}/events/scheduled",
        cookies={"session": sessions["user"]},
    )
    assert resp.status_code == 200, resp.text
    names = {e["name"] for e in resp.json()["events"]}
    assert "ActiveOne" in names
    assert "PastOne" not in names
    # active event carries signup fields
    active = next(e for e in resp.json()["events"] if e["name"] == "ActiveOne")
    assert active["id"] == str(active_id)
    assert active["web_signup_count"] == 0
    assert active["current_user_signed_up"] is False


@pytest.mark.asyncio
async def test_coordinator_sees_past_events(client, temp_db, sessions):
    await _create_event("PastForCoord", start_days=-5, end_days=-4)
    resp = await client.get(
        f"/api/guilds/{GUILD}/events/scheduled",
        cookies={"session": sessions["coordinator"]},
    )
    assert resp.status_code == 200, resp.text
    names = {e["name"] for e in resp.json()["events"]}
    assert "PastForCoord" in names


@pytest.mark.asyncio
async def test_regular_member_cannot_get_past_event_detail(client, temp_db, sessions):
    past_id = await _create_event("HiddenPast", start_days=-5, end_days=-4)
    resp = await client.get(
        f"/api/guilds/{GUILD}/events/scheduled/{past_id}",
        cookies={"session": sessions["user"]},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_regular_member_cannot_create_event(client, temp_db, sessions):
    resp = await client.post(
        f"/api/guilds/{GUILD}/events/scheduled",
        cookies={"session": sessions["user"]},
        json={
            "name": "Nope",
            "scheduled_start_time": _iso(1),
            "entity_type": "voice",
            "channel_id": "555000111",
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_regular_member_cannot_access_roster_export_message(
    client, temp_db, sessions
):
    eid = await _create_event("Guarded", start_days=1, end_days=2)
    cookies = {"session": sessions["user"]}
    assert (
        await client.get(f"/api/guilds/{GUILD}/events/{eid}/roster", cookies=cookies)
    ).status_code == 403
    assert (
        await client.get(f"/api/guilds/{GUILD}/events/{eid}/export", cookies=cookies)
    ).status_code == 403
    msg = await client.post(
        f"/api/guilds/{GUILD}/events/{eid}/message",
        cookies=cookies,
        json={"channel_id": "999", "message": "hi", "target": "all"},
    )
    assert msg.status_code == 403


@pytest.mark.asyncio
async def test_bot_owner_can_access_roster(client, temp_db, sessions):
    eid = await _create_event("OwnerEvent", start_days=1, end_days=2)
    resp = await client.get(
        f"/api/guilds/{GUILD}/events/{eid}/roster",
        cookies={"session": sessions["owner"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["event_id"] == eid


# ---------------------------------------------------------------------------
# Whole-event interest
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mark_and_withdraw_interest(client, temp_db, sessions):
    eid = await _create_event("InterestEvent", start_days=1, end_days=2)
    cookies = {"session": sessions["user"]}

    r1 = await client.post(f"/api/guilds/{GUILD}/events/{eid}/signup", cookies=cookies)
    assert r1.status_code == 201, r1.text
    assert r1.json()["signed_up"] is True
    assert r1.json()["web_signup_count"] == 1

    # Duplicate interest is prevented.
    r2 = await client.post(f"/api/guilds/{GUILD}/events/{eid}/signup", cookies=cookies)
    assert r2.status_code == 409

    # Withdraw hard-deletes the signup.
    r3 = await client.request(
        "DELETE", f"/api/guilds/{GUILD}/events/{eid}/signup", cookies=cookies
    )
    assert r3.status_code == 200, r3.text
    assert r3.json()["signed_up"] is False
    assert r3.json()["web_signup_count"] == 0


@pytest.mark.asyncio
async def test_cannot_signup_for_past_event(client, temp_db, sessions):
    past_id = await _create_event("PastSignup", start_days=-5, end_days=-4)
    resp = await client.post(
        f"/api/guilds/{GUILD}/events/{past_id}/signup",
        cookies={"session": sessions["user"]},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_signups_closed_rejects_interest(client, temp_db, sessions):
    eid = await _create_event("ClosedEvent", start_days=1, end_days=2)
    # Coordinator closes signups.
    patch = await client.patch(
        f"/api/guilds/{GUILD}/events/{eid}/settings",
        cookies={"session": sessions["coordinator"]},
        json={"signups_closed": True},
    )
    assert patch.status_code == 200, patch.text
    resp = await client.post(
        f"/api/guilds/{GUILD}/events/{eid}/signup",
        cookies={"session": sessions["user"]},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Roles + role signups
# ---------------------------------------------------------------------------
async def _create_role(client, session, eid, **kwargs):
    body = {"name": "Medic", "emoji": "🩺"}
    body.update(kwargs)
    return await client.post(
        f"/api/guilds/{GUILD}/events/{eid}/roles",
        cookies={"session": session},
        json=body,
    )


@pytest.mark.asyncio
async def test_coordinator_manages_roles(client, temp_db, sessions):
    eid = await _create_event("RoleEvent", start_days=1, end_days=2)
    coord = sessions["coordinator"]

    created = await _create_role(client, coord, eid, capacity=4, sort_order=1)
    assert created.status_code == 201, created.text
    role_id = created.json()["id"]

    updated = await client.patch(
        f"/api/guilds/{GUILD}/events/{eid}/roles/{role_id}",
        cookies={"session": coord},
        json={"locked": True, "capacity": 8},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["locked"] is True
    assert updated.json()["capacity"] == 8

    deleted = await client.request(
        "DELETE",
        f"/api/guilds/{GUILD}/events/{eid}/roles/{role_id}",
        cookies={"session": coord},
    )
    assert deleted.status_code == 200, deleted.text


@pytest.mark.asyncio
async def test_regular_member_cannot_manage_roles(client, temp_db, sessions):
    eid = await _create_event("RoleGuard", start_days=1, end_days=2)
    resp = await _create_role(client, sessions["user"], eid)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_role_capacity_enforced(client, temp_db, sessions):
    eid = await _create_event("CapEvent", start_days=1, end_days=2)
    created = await _create_role(client, sessions["coordinator"], eid, capacity=1)
    role_id = created.json()["id"]

    r1 = await client.post(
        f"/api/guilds/{GUILD}/events/{eid}/role-signup",
        cookies={"session": sessions["user"]},
        json={"role_id": role_id},
    )
    assert r1.status_code == 201, r1.text

    r2 = await client.post(
        f"/api/guilds/{GUILD}/events/{eid}/role-signup",
        cookies={"session": sessions["user2"]},
        json={"role_id": role_id},
    )
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_locked_role_rejects_regular_signup(client, temp_db, sessions):
    eid = await _create_event("LockEvent", start_days=1, end_days=2)
    created = await _create_role(client, sessions["coordinator"], eid, locked=True)
    role_id = created.json()["id"]

    resp = await client.post(
        f"/api/guilds/{GUILD}/events/{eid}/role-signup",
        cookies={"session": sessions["user"]},
        json={"role_id": role_id},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_multiple_role_signup_toggle(client, temp_db, sessions):
    eid = await _create_event("MultiEvent", start_days=1, end_days=2)
    coord = sessions["coordinator"]
    role_a = (await _create_role(client, coord, eid, name="A")).json()["id"]
    role_b = (await _create_role(client, coord, eid, name="B")).json()["id"]
    user = {"session": sessions["user"]}

    first = await client.post(
        f"/api/guilds/{GUILD}/events/{eid}/role-signup",
        cookies=user,
        json={"role_id": role_a},
    )
    assert first.status_code == 201, first.text

    # Multiple disabled by default -> second role rejected.
    second = await client.post(
        f"/api/guilds/{GUILD}/events/{eid}/role-signup",
        cookies=user,
        json={"role_id": role_b},
    )
    assert second.status_code == 409

    # Enable multiple role signups, then second role is allowed.
    patch = await client.patch(
        f"/api/guilds/{GUILD}/events/{eid}/settings",
        cookies={"session": coord},
        json={"allow_multiple_roles": True},
    )
    assert patch.status_code == 200, patch.text

    third = await client.post(
        f"/api/guilds/{GUILD}/events/{eid}/role-signup",
        cookies=user,
        json={"role_id": role_b},
    )
    assert third.status_code == 201, third.text


# ---------------------------------------------------------------------------
# Roster, export, messaging (coordinator)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_roster_separates_no_role_and_roles(client, temp_db, sessions):
    eid = await _create_event("RosterEvent", start_days=1, end_days=2)
    coord = sessions["coordinator"]
    role_id = (await _create_role(client, coord, eid, capacity=4)).json()["id"]

    # user1 picks a role; user2 only marks interest.
    await client.post(
        f"/api/guilds/{GUILD}/events/{eid}/role-signup",
        cookies={"session": sessions["user"]},
        json={"role_id": role_id},
    )
    await client.post(
        f"/api/guilds/{GUILD}/events/{eid}/signup",
        cookies={"session": sessions["user2"]},
    )

    roster = await client.get(
        f"/api/guilds/{GUILD}/events/{eid}/roster", cookies={"session": coord}
    )
    assert roster.status_code == 200, roster.text
    data = roster.json()
    assert data["total_web_signups"] == 2
    assert {u["user_id"] for u in data["no_role_users"]} == {"700000002"}
    role_block = next(r for r in data["roles"] if r["role_id"] == role_id)
    assert {u["user_id"] for u in role_block["users"]} == {"700000001"}


@pytest.mark.asyncio
async def test_csv_export_contains_signups(client, temp_db, sessions):
    eid = await _create_event("ExportEvent", start_days=1, end_days=2)
    await client.post(
        f"/api/guilds/{GUILD}/events/{eid}/signup",
        cookies={"session": sessions["user"]},
    )
    resp = await client.get(
        f"/api/guilds/{GUILD}/events/{eid}/export",
        cookies={"session": sessions["coordinator"]},
    )
    assert resp.status_code == 200, resp.text
    assert "text/csv" in resp.headers["content-type"]
    body = resp.text
    assert "user_id" in body
    assert "700000001" in body
    assert ",web" in body


@pytest.mark.asyncio
async def test_coordinator_message_targets_signups(
    client, temp_db, sessions, fake_internal_api
):
    eid = await _create_event("MsgEvent", start_days=1, end_days=2)
    await client.post(
        f"/api/guilds/{GUILD}/events/{eid}/signup",
        cookies={"session": sessions["user"]},
    )

    sent = {}

    async def _send(guild_id, channel_id, message, user_ids=None):
        sent["guild_id"] = guild_id
        sent["channel_id"] = channel_id
        sent["user_ids"] = user_ids
        return {"success": True, "recipients": len(user_ids or [])}

    fake_internal_api.send_channel_message = _send

    resp = await client.post(
        f"/api/guilds/{GUILD}/events/{eid}/message",
        cookies={"session": sessions["coordinator"]},
        json={"channel_id": "555000111", "message": "Hello", "target": "all"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["recipients"] == 1
    assert sent["user_ids"] == ["700000001"]
    assert sent["channel_id"] == 555000111
