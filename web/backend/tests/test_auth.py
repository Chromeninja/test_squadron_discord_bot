"""
Tests for authentication endpoints.
"""

from typing import Any
from unittest.mock import MagicMock
from urllib.parse import ParseResult, parse_qs, urlparse

import httpx
import pytest
from core.security import (
    create_session_token_async,
    decode_session_token,
    generate_oauth_state,
)
from httpx import AsyncClient

pytestmark: pytest.MarkDecorator = pytest.mark.contract


@pytest.mark.asyncio
async def test_auth_me_no_session(client: AsyncClient) -> None:
    """Test /api/auth/me without session returns null user."""
    response: httpx.Response = await client.get("/api/auth/me")

    # Should succeed but user should be None
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["user"] is None


@pytest.mark.asyncio
async def test_auth_me_with_admin_session(
    client: AsyncClient, mock_admin_session: str
) -> None:
    """Test /api/auth/me with valid admin session."""
    response: httpx.Response = await client.get(
        "/api/auth/me",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["user"] is not None
    assert data["user"]["user_id"] == "246604397155581954"
    assert "authorized_guilds" in data["user"]
    assert "123" in data["user"]["authorized_guilds"]
    assert data["user"]["authorized_guilds"]["123"]["role_level"] == "bot_admin"


@pytest.mark.asyncio
async def test_assume_role_downgrades_bot_owner_session(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bot owners should be able to assume lower roles for dashboard testing."""
    audit_calls: list[dict[str, Any]] = []

    async def fake_log_admin_action(**kwargs: Any) -> None:
        audit_calls.append(kwargs)

    monkeypatch.setattr("routes.auth.log_admin_action", fake_log_admin_action)

    owner_session: str = await create_session_token_async(
        {
            "user_id": "246604397155581954",
            "username": "TestOwner",
            "discriminator": "0001",
            "avatar": None,
            "active_guild_id": "123",
            "is_bot_owner": True,
            "authorized_guilds": {
                "123": {
                    "guild_id": "123",
                    "role_level": "bot_owner",
                    "source": "bot_owner",
                }
            },
        }
    )

    response: httpx.Response = await client.post(
        "/api/auth/assume-role",
        json={"role_level": "staff"},
        cookies={"session": owner_session},
    )

    assert response.status_code == 200
    data = response.json()
    permission = data["user"]["authorized_guilds"]["123"]
    assert permission["base_role_level"] == "bot_owner"
    assert permission["assumed_role_level"] == "staff"
    assert permission["role_level"] == "staff"

    new_session: str | None = response.cookies.get("session")
    assert new_session
    decoded = await decode_session_token(new_session)
    assert decoded is not None
    assert decoded["authorized_guilds"]["123"]["assumed_role_level"] == "staff"
    assert audit_calls == [
        {
            "admin_user_id": 246604397155581954,
            "guild_id": 123,
            "action": "ASSUME_DASHBOARD_ROLE",
            "details": {"base_role": "bot_owner", "assumed_role": "staff"},
            "status": "success",
        }
    ]


@pytest.mark.asyncio
async def test_clear_assumed_role_restores_bot_owner_session(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clearing an assumed role should restore the base effective role."""
    audit_calls: list[dict[str, Any]] = []

    async def fake_log_admin_action(**kwargs: Any) -> None:
        audit_calls.append(kwargs)

    monkeypatch.setattr("routes.auth.log_admin_action", fake_log_admin_action)

    owner_session: str = await create_session_token_async(
        {
            "user_id": "246604397155581954",
            "username": "TestOwner",
            "discriminator": "0001",
            "avatar": None,
            "active_guild_id": "123",
            "is_bot_owner": True,
            "authorized_guilds": {
                "123": {
                    "guild_id": "123",
                    "role_level": "staff",
                    "base_role_level": "bot_owner",
                    "assumed_role_level": "staff",
                    "source": "bot_owner",
                }
            },
        }
    )

    response: httpx.Response = await client.delete(
        "/api/auth/assume-role",
        cookies={"session": owner_session},
    )

    assert response.status_code == 200
    permission = response.json()["user"]["authorized_guilds"]["123"]
    assert permission["base_role_level"] == "bot_owner"
    assert permission["assumed_role_level"] is None
    assert permission["role_level"] == "bot_owner"
    assert audit_calls == [
        {
            "admin_user_id": 246604397155581954,
            "guild_id": 123,
            "action": "CLEAR_ASSUMED_DASHBOARD_ROLE",
            "details": {"base_role": "bot_owner"},
            "status": "success",
        }
    ]


@pytest.mark.asyncio
async def test_assume_role_rejects_non_bot_owner(
    client: AsyncClient,
    mock_admin_session: str,
) -> None:
    """Only bot owners can assume dashboard roles."""
    response: httpx.Response = await client.post(
        "/api/auth/assume-role",
        json={"role_level": "staff"},
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_assume_role_rejects_bot_owner_target(client: AsyncClient) -> None:
    """Role switching should not allow assuming bot_owner as a target."""
    owner_session: str = await create_session_token_async(
        {
            "user_id": "246604397155581954",
            "username": "TestOwner",
            "discriminator": "0001",
            "avatar": None,
            "active_guild_id": "123",
            "is_bot_owner": True,
            "authorized_guilds": {
                "123": {
                    "guild_id": "123",
                    "role_level": "bot_owner",
                    "source": "bot_owner",
                }
            },
        }
    )

    response: httpx.Response = await client.post(
        "/api/auth/assume-role",
        json={"role_level": "bot_owner"},
        cookies={"session": owner_session},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_auth_me_with_moderator_session(
    client: AsyncClient, mock_moderator_session: str
) -> None:
    """Test /api/auth/me with valid moderator session."""
    response: httpx.Response = await client.get(
        "/api/auth/me",
        cookies={"session": mock_moderator_session},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["user"] is not None
    assert data["user"]["user_id"] == "1428084144860303511"
    assert "authorized_guilds" in data["user"]
    assert "123" in data["user"]["authorized_guilds"]
    assert data["user"]["authorized_guilds"]["123"]["role_level"] == "moderator"


@pytest.mark.asyncio
async def test_login_redirect(client: AsyncClient) -> None:
    """Test /auth/login redirects to Discord."""
    response: httpx.Response = await client.get("/auth/login", follow_redirects=False)

    assert response.status_code == 307  # Redirect
    redirect_url: str = response.headers["location"]
    parsed: ParseResult = urlparse(redirect_url)

    assert parsed.scheme == "https"
    assert parsed.hostname == "discord.com"
    assert parsed.path == "/api/oauth2/authorize"

    query_params: dict[str, list[str]] = parse_qs(parsed.query)
    # Verify state parameter is included for CSRF protection
    assert query_params.get("state")


@pytest.mark.asyncio
async def test_callback_rejects_invalid_state(client: AsyncClient) -> None:
    """Test that callback rejects requests with invalid or missing state token."""
    # Test with missing state
    response: httpx.Response = await client.get(
        "/auth/callback",
        params={"code": "test_code"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "state" in response.text.lower()

    # Test with invalid state
    response_invalid: httpx.Response = await client.get(
        "/auth/callback",
        params={"code": "test_code", "state": "invalid_state_token"},
        follow_redirects=False,
    )
    assert response_invalid.status_code == 400
    assert "state" in response_invalid.text.lower()


@pytest.mark.asyncio
async def test_oauth_state_is_one_time_use(client: AsyncClient) -> None:
    """Test that OAuth state tokens can only be used once (prevents replay attacks)."""
    from core.security import generate_oauth_state, validate_oauth_state

    # Generate a state
    state: str = generate_oauth_state()

    # First validation should succeed
    assert validate_oauth_state(state) is True

    # Second validation with same state should fail (already consumed)
    assert validate_oauth_state(state) is False


@pytest.mark.asyncio
async def test_oauth_state_expires_after_5_minutes(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that OAuth state tokens expire after 5 minutes."""
    from datetime import UTC, datetime

    from core.security import _oauth_states, generate_oauth_state, validate_oauth_state

    # Generate a state
    state: str = generate_oauth_state()

    # Manually backdate the state timestamp to simulate expiration
    # State was created "6 minutes ago" (360 seconds)
    _oauth_states[state] = datetime.now(UTC).timestamp() - 360

    # Validation should fail due to expiration
    assert validate_oauth_state(state) is False


@pytest.mark.asyncio
async def test_cleanup_expired_states() -> None:
    """Test that expired OAuth states are properly cleaned up."""
    from datetime import UTC, datetime

    from core.security import (
        _oauth_states,
        cleanup_expired_states,
        generate_oauth_state,
    )

    # Generate some states
    fresh_state: str = generate_oauth_state()
    old_state: str = generate_oauth_state()

    # Backdate one state to make it expired
    _oauth_states[old_state] = datetime.now(UTC).timestamp() - 400  # >5 minutes

    # Run cleanup
    cleanup_expired_states()

    # Fresh state should still exist, old state should be removed
    assert fresh_state in _oauth_states
    assert old_state not in _oauth_states

    # Clean up the fresh state for test isolation
    _oauth_states.pop(fresh_state, None)


@pytest.mark.asyncio
async def test_get_guilds_returns_active_list(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api: Any,
) -> None:
    """Ensure /api/auth/guilds proxies through the internal API client."""
    fake_internal_api.guilds = [
        {"guild_id": 1, "guild_name": "Alpha", "icon_url": "https://example.com/a.png"},
        {"guild_id": 2, "guild_name": "Bravo", "icon_url": None},
    ]

    response: httpx.Response = await client.get(
        "/api/auth/guilds",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["guilds"]) == 2
    assert data["guilds"][0]["guild_name"] == "Alpha"


@pytest.mark.asyncio
async def test_select_guild_sets_session_cookie(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api: Any,
) -> None:
    """Selecting a guild should update the session cookie with the guild ID."""
    fake_internal_api.guilds = [
        {"guild_id": 123, "guild_name": "Alpha", "icon_url": None},
    ]

    response: httpx.Response = await client.post(
        "/api/auth/select-guild",
        json={"guild_id": "123"},
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    new_session: str | None = response.cookies.get("session")
    assert new_session

    decoded = await decode_session_token(new_session)
    assert decoded is not None
    assert decoded["active_guild_id"] == "123"


@pytest.mark.asyncio
async def test_select_guild_rejects_unknown_guild(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api: Any,
) -> None:
    fake_internal_api.guilds = [
        {"guild_id": 999, "guild_name": "Known", "icon_url": None},
    ]

    response: httpx.Response = await client.post(
        "/api/auth/select-guild",
        json={"guild_id": "1000"},
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Guild not found"


@pytest.mark.asyncio
async def test_select_guild_allows_when_internal_api_empty(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api: Any,
) -> None:
    fake_internal_api.guilds = []

    response: httpx.Response = await client.post(
        "/api/auth/select-guild",
        json={"guild_id": "321"},
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_guilds_falls_back_to_session_when_internal_api_unavailable(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api: Any,
) -> None:
    """Guild list should remain available from the session during internal API outages."""

    async def raise_request_error(*args: Any, **kwargs: Any) -> list[dict]:
        request = httpx.Request("GET", "http://test/internal")
        raise httpx.RequestError("internal api unavailable", request=request)

    fake_internal_api.get_guilds = raise_request_error
    fake_internal_api.get_guild_member = raise_request_error

    response: httpx.Response = await client.get(
        "/api/auth/guilds?force_refresh=1",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert [guild["guild_id"] for guild in data["guilds"]] == ["123", "1", "2"]


@pytest.mark.asyncio
async def test_get_guilds_fallback_excludes_non_installed_session_guilds(
    client: AsyncClient,
    fake_internal_api: Any,
) -> None:
    """Fallback mode should never return guilds missing from guild_settings."""

    custom_session: str = await create_session_token_async(
        {
            "user_id": "246604397155581954",
            "username": "TestAdmin",
            "discriminator": "0001",
            "avatar": None,
            "active_guild_id": "123",
            "authorized_guilds": {
                "123": {
                    "guild_id": "123",
                    "role_level": "bot_admin",
                    "source": "bot_admin_role",
                },
                "555": {
                    "guild_id": "555",
                    "role_level": "bot_admin",
                    "source": "bot_admin_role",
                },
            },
        }
    )

    async def raise_request_error(*args: Any, **kwargs: Any) -> list[dict]:
        request = httpx.Request("GET", "http://test/internal")
        raise httpx.RequestError("internal api unavailable", request=request)

    fake_internal_api.get_guilds = raise_request_error

    response: httpx.Response = await client.get(
        "/api/auth/guilds?force_refresh=1",
        cookies={"session": custom_session},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert [guild["guild_id"] for guild in data["guilds"]] == ["123"]


@pytest.mark.asyncio
async def test_select_guild_uses_session_guilds_when_internal_api_unavailable(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api: Any,
) -> None:
    """Guild selection should continue to work for already-authorized guilds."""

    async def raise_request_error(*args: Any, **kwargs: Any) -> list[dict]:
        request = httpx.Request("GET", "http://test/internal")
        raise httpx.RequestError("internal api unavailable", request=request)

    fake_internal_api.get_guilds = raise_request_error
    fake_internal_api.get_guild_member = raise_request_error

    response: httpx.Response = await client.post(
        "/api/auth/select-guild",
        json={"guild_id": "123"},
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 200
    new_session: str | None = response.cookies.get("session")
    assert new_session

    decoded = await decode_session_token(new_session)
    assert decoded is not None
    assert decoded["active_guild_id"] == "123"


@pytest.mark.asyncio
async def test_get_guilds_downgrades_to_user_on_role_mismatch(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api: Any,
) -> None:
    """A member who lost an elevated role is downgraded to ``user``, not revoked.

    Regular guild members must keep dashboard access (Events page), so a live
    role mismatch for someone still in the guild downgrades their base role to
    ``user`` rather than removing the guild from their session.
    """

    async def mismatched_member(guild_id: int, user_id: int) -> dict:
        return {
            "user_id": user_id,
            "role_ids": ["not-a-valid-role"],
            "source": "discord",
        }

    fake_internal_api.get_guild_member = mismatched_member

    response: httpx.Response = await client.get(
        "/api/auth/guilds?force_refresh=1",
        cookies={"session": mock_admin_session},
    )

    # Access is retained (still a member), not revoked.
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_guilds_revokes_access_when_not_in_guild(
    client: AsyncClient,
    mock_admin_session: str,
    fake_internal_api: Any,
) -> None:
    """Users no longer in a guild (404 on member lookup) are still revoked."""
    import httpx as _httpx

    async def missing_member(guild_id: int, user_id: int) -> dict:
        request = _httpx.Request("GET", "http://internal/member")
        response = _httpx.Response(404, request=request)
        raise _httpx.HTTPStatusError("not found", request=request, response=response)

    fake_internal_api.get_guild_member = missing_member

    response: httpx.Response = await client.get(
        "/api/auth/guilds?force_refresh=1",
        cookies={"session": mock_admin_session},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "role_revoked"


@pytest.mark.asyncio
async def test_callback_grants_access_to_guild_owner(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that guild owners are granted admin access even without configured roles."""
    from unittest.mock import AsyncMock

    async def mock_post(*args: Any, **kwargs: Any) -> Any:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = lambda: {
            "access_token": "mock_token",
            "token_type": "Bearer",
        }
        return mock_response

    async def mock_get(url: str, *args: Any, **kwargs: Any) -> Any:
        mock_response = MagicMock()
        mock_response.status_code = 200

        if "/users/@me/guilds" in url and "/member" not in url:
            mock_response.json = lambda: [
                {
                    "id": "123",
                    "name": "Test Guild",
                    "owner": True,
                    "permissions": "2147483647",
                }
            ]
        elif "/users/@me" in url:
            mock_response.json = lambda: {
                "id": "123456789",
                "username": "TestOwner",
                "discriminator": "0001",
                "avatar": None,
            }

        return mock_response

    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=mock_post)
    mock_client.get = AsyncMock(side_effect=mock_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setattr(
        "routes.auth.httpx.AsyncClient", lambda *args, **kwargs: mock_client
    )

    valid_state: str = generate_oauth_state()

    response: httpx.Response = await client.get(
        "/auth/callback",
        params={"code": "test_code", "state": valid_state},
        follow_redirects=False,
    )

    assert response.status_code == 307

    session_cookie: str | None = response.cookies.get("session")
    assert session_cookie is not None

    from core.security import decode_session_token

    session_data = await decode_session_token(session_cookie)
    assert session_data is not None
    assert "123" in session_data["authorized_guilds"]
    guild_permission = session_data["authorized_guilds"]["123"]
    assert guild_permission["role_level"] == "bot_admin"
    assert guild_permission["source"] == "discord_owner"


@pytest.mark.asyncio
async def test_callback_redirects_to_preserved_next_path(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OAuth callback should redirect to the state-preserved frontend path."""
    from unittest.mock import AsyncMock

    async def mock_post(*args: Any, **kwargs: Any) -> Any:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = lambda: {
            "access_token": "mock_token",
            "token_type": "Bearer",
        }
        return mock_response

    async def mock_get(url: str, *args: Any, **kwargs: Any) -> Any:
        mock_response = MagicMock()
        mock_response.status_code = 200

        if "/users/@me/guilds" in url and "/member" not in url:
            mock_response.json = lambda: [
                {
                    "id": "123",
                    "name": "Test Guild",
                    "owner": True,
                    "permissions": "2147483647",
                }
            ]
        elif "/users/@me" in url:
            mock_response.json = lambda: {
                "id": "123456789",
                "username": "TestOwner",
                "discriminator": "0001",
                "avatar": None,
            }

        return mock_response

    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=mock_post)
    mock_client.get = AsyncMock(side_effect=mock_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setattr(
        "routes.auth.httpx.AsyncClient", lambda *args, **kwargs: mock_client
    )

    valid_state: str = generate_oauth_state(next_path="/dashboard/123/metrics")

    response: httpx.Response = await client.get(
        "/auth/callback",
        params={"code": "test_code", "state": valid_state},
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"].endswith("/dashboard/123/metrics")


@pytest.mark.asyncio
async def test_callback_grants_access_to_administrator(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that users with Discord administrator permission are granted admin access."""
    from unittest.mock import AsyncMock

    async def mock_post(*args: Any, **kwargs: Any) -> Any:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = lambda: {
            "access_token": "mock_token",
            "token_type": "Bearer",
        }
        return mock_response

    async def mock_get(url: str, *args: Any, **kwargs: Any) -> Any:
        mock_response = MagicMock()
        mock_response.status_code = 200

        if "/users/@me/guilds" in url and "/member" not in url:
            mock_response.json = lambda: [
                {
                    "id": "123",
                    "name": "Test Guild",
                    "owner": False,
                    "permissions": "8",
                }
            ]
        elif "/users/@me" in url:
            mock_response.json = lambda: {
                "id": "987654321",
                "username": "TestAdmin",
                "discriminator": "0002",
                "avatar": None,
            }

        return mock_response

    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=mock_post)
    mock_client.get = AsyncMock(side_effect=mock_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setattr(
        "routes.auth.httpx.AsyncClient", lambda *args, **kwargs: mock_client
    )

    valid_state: str = generate_oauth_state()

    response: httpx.Response = await client.get(
        "/auth/callback",
        params={"code": "test_code", "state": valid_state},
        follow_redirects=False,
    )

    assert response.status_code == 307

    session_cookie: str | None = response.cookies.get("session")
    assert session_cookie is not None

    from core.security import decode_session_token

    session_data = await decode_session_token(session_cookie)
    assert session_data is not None
    assert "123" in session_data["authorized_guilds"]
    guild_permission = session_data["authorized_guilds"]["123"]
    assert guild_permission["role_level"] == "bot_admin"
    assert guild_permission["source"] == "discord_administrator"


@pytest.mark.asyncio
async def test_callback_denies_access_without_permissions(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that users without owner/admin/configured roles are denied access."""
    from unittest.mock import AsyncMock

    # Mock OAuth token exchange
    async def mock_post(*args: Any, **kwargs: Any) -> MagicMock:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = lambda: {
            "access_token": "mock_token",
            "token_type": "Bearer",
        }
        return mock_response

    # Mock Discord API calls
    async def mock_get(url: str, *args: Any, **kwargs: Any) -> MagicMock:
        mock_response = MagicMock()
        mock_response.status_code = 200

        if "/users/@me/guilds" in url and "/member" not in url:
            # Return guilds where user has no special permissions
            mock_response.json = lambda: [
                {
                    "id": "246486575137947648",
                    "name": "Test Guild",
                    "owner": False,
                    "permissions": "0",  # No permissions
                }
            ]
        elif "/users/@me/guilds/" in url and "/member" in url:
            # Return member with no configured roles
            mock_response.json = lambda: {
                "roles": [],  # No roles
            }
        elif "/users/@me" in url:
            # Return user info
            mock_response.json = lambda: {
                "id": "111222333",
                "username": "TestUser",
                "discriminator": "0003",
                "avatar": None,
            }

        return mock_response

    # Mock httpx client
    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=mock_post)
    mock_client.get = AsyncMock(side_effect=mock_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setattr(
        "routes.auth.httpx.AsyncClient", lambda *args, **kwargs: mock_client
    )

    # Generate valid OAuth state for CSRF validation
    valid_state: str = generate_oauth_state()

    response: httpx.Response = await client.get(
        "/auth/callback",
        params={"code": "test_code", "state": valid_state},
        follow_redirects=False,
    )

    # Should return 403 Access Denied
    assert response.status_code == 403
    assert "Access Denied" in response.text


@pytest.mark.asyncio
async def test_callback_bot_owner_excludes_non_installed_guilds(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bot-owner sessions should include only guilds where the bot is configured."""
    from unittest.mock import AsyncMock

    async def mock_post(*args: Any, **kwargs: Any) -> MagicMock:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = lambda: {
            "access_token": "mock_token",
            "token_type": "Bearer",
        }
        return mock_response

    async def mock_get(url: str, *args: Any, **kwargs: Any) -> MagicMock:
        mock_response = MagicMock()
        mock_response.status_code = 200

        if "/users/@me/guilds" in url and "/member" not in url:
            mock_response.json = lambda: [
                {
                    "id": "123",
                    "name": "Installed Guild",
                    "owner": False,
                    "permissions": "0",
                },
                {
                    "id": "555",
                    "name": "Not Installed Guild",
                    "owner": False,
                    "permissions": "0",
                },
            ]
        elif "/users/@me" in url:
            mock_response.json = lambda: {
                "id": "123456789",
                "username": "TestOwner",
                "discriminator": "0001",
                "avatar": None,
            }

        return mock_response

    class MockInternalAPIClient:
        async def get_bot_owner_ids(self) -> list[int]:
            return [123456789]

        async def close(self) -> None:
            return None

    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=mock_post)
    mock_client.get = AsyncMock(side_effect=mock_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setattr(
        "routes.auth.httpx.AsyncClient", lambda *args, **kwargs: mock_client
    )
    monkeypatch.setattr("routes.auth.InternalAPIClient", MockInternalAPIClient)

    valid_state: str = generate_oauth_state()
    response: httpx.Response = await client.get(
        "/auth/callback",
        params={"code": "test_code", "state": valid_state},
        follow_redirects=False,
    )

    assert response.status_code == 307

    session_cookie: str | None = response.cookies.get("session")
    assert session_cookie is not None

    session_data = await decode_session_token(session_cookie)
    assert session_data is not None
    assert set(session_data["authorized_guilds"]) == {"123"}
    assert session_data["authorized_guilds"]["123"]["role_level"] == "bot_owner"


@pytest.mark.asyncio
async def test_callback_allows_bot_owner_with_no_installed_guilds(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bot owners should be able to complete OAuth when no guild is installed yet."""
    from unittest.mock import AsyncMock

    async def mock_post(*args: Any, **kwargs: Any) -> MagicMock:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = lambda: {
            "access_token": "mock_token",
            "token_type": "Bearer",
        }
        return mock_response

    async def mock_get(url: str, *args: Any, **kwargs: Any) -> MagicMock:
        mock_response = MagicMock()
        mock_response.status_code = 200

        if "/users/@me/guilds" in url and "/member" not in url:
            mock_response.json = lambda: [
                {
                    "id": "555",
                    "name": "New Guild",
                    "owner": True,
                    "permissions": "2147483647",
                }
            ]
        elif "/users/@me" in url:
            mock_response.json = lambda: {
                "id": "123456789",
                "username": "BootstrapOwner",
                "discriminator": "0001",
                "avatar": None,
            }

        return mock_response

    class MockInternalAPIClient:
        async def get_bot_owner_ids(self) -> list[int]:
            return [123456789]

        async def get_guilds(self) -> list[dict]:
            return []

        async def close(self) -> None:
            return None

    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=mock_post)
    mock_client.get = AsyncMock(side_effect=mock_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    async def fetch_all_empty(*args: Any, **kwargs: Any) -> list[Any]:
        return []

    monkeypatch.setattr(
        "routes.auth.httpx.AsyncClient", lambda *args, **kwargs: mock_client
    )
    monkeypatch.setattr("routes.auth.InternalAPIClient", MockInternalAPIClient)
    monkeypatch.setattr(
        "services.db.repository.BaseRepository.fetch_all",
        fetch_all_empty,
    )

    valid_state: str = generate_oauth_state()
    response: httpx.Response = await client.get(
        "/auth/callback",
        params={"code": "test_code", "state": valid_state},
        follow_redirects=False,
    )

    assert response.status_code == 307

    session_cookie: str | None = response.cookies.get("session")
    assert session_cookie is not None

    session_data = await decode_session_token(session_cookie)
    assert session_data is not None
    assert session_data["is_bot_owner"] is True
    assert session_data["authorized_guilds"] == {}


@pytest.mark.asyncio
async def test_get_guilds_allows_bot_owner_with_no_authorized_guilds(
    client: AsyncClient,
    fake_internal_api: Any,
) -> None:
    """Bot owners should be able to load empty guild list before any install."""
    empty_owner_session: str = await create_session_token_async(
        {
            "user_id": "246604397155581954",
            "username": "Owner",
            "discriminator": "0001",
            "avatar": None,
            "active_guild_id": None,
            "is_bot_owner": True,
            "authorized_guilds": {},
        }
    )

    fake_internal_api.guilds = []

    response: httpx.Response = await client.get(
        "/api/auth/guilds",
        cookies={"session": empty_owner_session},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["guilds"] == []


# ---------------------------------------------------------------------------
# Session Expiration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_token_contains_expiration() -> None:
    """Session tokens should store issued/expiry metadata in server payload."""

    user_data: dict[str, str] = {"user_id": "123", "username": "test"}
    token: str = await create_session_token_async(user_data)

    decoded = await decode_session_token(token)
    assert decoded is not None
    assert "exp" in decoded
    assert "iat" in decoded
    assert decoded["user_id"] == "123"


@pytest.mark.asyncio
async def test_expired_session_token_rejected() -> None:
    """Expired server-side session should not resolve."""

    expired_token: str = await create_session_token_async(
        {"user_id": "123", "username": "test"}, expires_in_seconds=0
    )

    result = await decode_session_token(expired_token)
    assert result is None


@pytest.mark.asyncio
async def test_expired_session_returns_null_user(client: AsyncClient) -> None:
    """API should gracefully return null user for expired session cookie."""

    expired_token: str = await create_session_token_async(
        {"user_id": "123", "username": "test"}, expires_in_seconds=0
    )

    response: httpx.Response = await client.get(
        "/api/auth/me",
        cookies={"session": expired_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["user"] is None


@pytest.mark.asyncio
async def test_tampered_session_token_rejected() -> None:
    """Tampered signed tokens should fail signature validation."""

    valid_token: str = await create_session_token_async(
        {"user_id": "123", "username": "test"}
    )
    tampered_token: str = valid_token + "broken"

    result = await decode_session_token(tampered_token)
    assert result is None


@pytest.mark.asyncio
async def test_session_max_age_is_7_days() -> None:
    """Test that session configuration uses 7-day expiration."""
    from core.security import JWT_EXPIRATION_HOURS, SESSION_MAX_AGE

    # Cookie max age should be 7 days in seconds
    assert SESSION_MAX_AGE == 86400 * 7  # 604800 seconds

    # JWT expiration should be 7 days in hours
    assert JWT_EXPIRATION_HOURS == 24 * 7  # 168 hours


@pytest.mark.asyncio
async def test_bot_invite_url_uses_least_privilege_permissions(
    client: AsyncClient,
) -> None:
    """Bot invite URL should not request Administrator permissions by default."""

    owner_session: str = await create_session_token_async(
        {
            "user_id": "1",
            "username": "BotOwner",
            "discriminator": "0001",
            "avatar": None,
            "authorized_guilds": {},
            "is_bot_owner": True,
        }
    )

    response: httpx.Response = await client.get(
        "/api/auth/bot-invite-url",
        cookies={"session": owner_session},
    )

    assert response.status_code == 200
    invite_url = response.json().get("invite_url")
    assert invite_url

    parsed = urlparse(invite_url)
    query = parse_qs(parsed.query)

    assert query.get("scope") == ["bot applications.commands"]
    assert query.get("permissions") == ["4409305189648"]
    assert query.get("redirect_uri")
    assert query["redirect_uri"][0].endswith("/auth/bot-callback")
