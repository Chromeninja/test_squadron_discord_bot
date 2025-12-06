import pytest
from core.security import SESSION_COOKIE_NAME
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_delegation_policies_default_empty(
    client: AsyncClient, mock_admin_session: str
):
    response = await client.get(
        "/api/roles/delegation", cookies={SESSION_COOKIE_NAME: mock_admin_session}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["policies"] == []


@pytest.mark.asyncio
async def test_set_and_get_delegation_policies(
    client: AsyncClient, mock_admin_session: str
):
    payload = {
        "policies": [
            {
                "grantor_role_ids": ["111", "222", "222"],
                "target_role_id": "333",
                "prerequisite_role_ids_all": ["444"],
                "prerequisite_role_ids_any": ["445"],
                "enabled": True,
                "note": "division chiefs may grant",
            }
        ]
    }

    resp = await client.post(
        "/api/roles/delegation",
        json=payload,
        cookies={SESSION_COOKIE_NAME: mock_admin_session},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["policies"][0]["grantor_role_ids"] == ["111", "222"]
    assert body["data"]["policies"][0]["target_role_id"] == "333"
    assert body["data"]["policies"][0]["prerequisite_role_ids_all"] == ["444"]
    assert body["data"]["policies"][0]["prerequisite_role_ids_any"] == ["445"]

    # Fetch back and ensure persistence/normalization
    follow = await client.get(
        "/api/roles/delegation", cookies={SESSION_COOKIE_NAME: mock_admin_session}
    )
    assert follow.status_code == 200
    data = follow.json()["data"]["policies"]
    assert data == body["data"]["policies"]
