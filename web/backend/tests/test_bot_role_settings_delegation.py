import pytest
from core.security import SESSION_COOKIE_NAME
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_bot_role_settings_default_delegation_empty(
    client: AsyncClient, mock_admin_session: str
):
    resp = await client.get(
        "/api/guilds/123/settings/bot-roles",
        cookies={SESSION_COOKIE_NAME: mock_admin_session},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("delegation_policies") == []


@pytest.mark.asyncio
async def test_bot_role_settings_set_and_roundtrip_delegation(
    client: AsyncClient, mock_admin_session: str
):
    payload = {
        "bot_admins": ["999111222"],
        "discord_managers": [],
        "moderators": [],
        "staff": [],
        "bot_verified_role": [],
        "main_role": [],
        "affiliate_role": [],
        "nonmember_role": [],
        "delegation_policies": [
            {
                "grantor_role_ids": ["10", "10", "abc"],
                "target_role_id": "42",
                "prerequisite_role_ids_all": ["7", "nan"],
                "prerequisite_role_ids_any": ["8"],
                "enabled": False,
                "note": "test delegation",
            }
        ],
    }

    put_resp = await client.put(
        "/api/guilds/123/settings/bot-roles",
        json=payload,
        cookies={SESSION_COOKIE_NAME: mock_admin_session},
    )
    assert put_resp.status_code == 200
    saved = put_resp.json()

    policy = saved["delegation_policies"][0]
    assert policy["grantor_role_ids"] == ["10"]
    assert policy["target_role_id"] == "42"
    assert policy["prerequisite_role_ids_all"] == ["7"]
    assert policy["prerequisite_role_ids_any"] == ["8"]
    assert policy["prerequisite_role_ids"] == ["7"]
    assert policy["enabled"] is False
    assert policy["note"] == "test delegation"

    get_resp = await client.get(
        "/api/guilds/123/settings/bot-roles",
        cookies={SESSION_COOKIE_NAME: mock_admin_session},
    )
    assert get_resp.status_code == 200
    roundtrip = get_resp.json()["delegation_policies"]
    assert roundtrip == saved["delegation_policies"]
