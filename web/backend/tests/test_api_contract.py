"""
Contract Tests for FastAPI Endpoints

Integration tests using in-memory database and fake auth.
Tests verification status and voice settings endpoints.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.contract
class TestVerificationStatusEndpoint:
    """Contract tests for verification status API endpoint."""

    @pytest.mark.asyncio
    async def test_verification_status_returns_correct_shape(
        self, client: AsyncClient, mock_admin_session: str
    ):
        """Contract: Verification search returns expected payload shape."""
        response = await client.get(
            "/api/users/search?query=123456789",
            cookies={"session": mock_admin_session},
        )

        assert response.status_code == 200
        data = response.json()

        # Contract: Response structure
        assert "success" in data
        assert "total" in data
        assert "items" in data
        assert "page" in data
        assert "page_size" in data

        # Contract: Item structure (when results exist)
        if data["total"] > 0:
            item = data["items"][0]
            assert "user_id" in item
            assert "rsi_handle" in item
            assert "membership_status" in item

    @pytest.mark.asyncio
    async def test_verification_status_main_member(
        self, client: AsyncClient, mock_admin_session: str
    ):
        """Contract: Main org member has correct membership status."""
        # User 123456789 is seeded with main_orgs = '["TEST"]'
        response = await client.get(
            "/api/users/search?query=123456789",
            cookies={"session": mock_admin_session},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 1
        item = data["items"][0]
        assert item["user_id"] == 123456789
        assert item["membership_status"] == "main"

    @pytest.mark.asyncio
    async def test_verification_status_affiliate_member(
        self, client: AsyncClient, mock_admin_session: str
    ):
        """Contract: Affiliate member has correct membership status."""
        # User 987654321 is seeded with affiliate_orgs = '["TEST"]'
        response = await client.get(
            "/api/users/search?query=987654321",
            cookies={"session": mock_admin_session},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 1
        item = data["items"][0]
        assert item["user_id"] == 987654321
        assert item["membership_status"] == "affiliate"

    @pytest.mark.asyncio
    async def test_verification_status_non_member(
        self, client: AsyncClient, mock_admin_session: str
    ):
        """Contract: Non-member has correct membership status."""
        # User 111222333 is seeded with main_orgs = '[]', affiliate_orgs = '[]'
        response = await client.get(
            "/api/users/search?query=111222333",
            cookies={"session": mock_admin_session},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 1
        item = data["items"][0]
        assert item["user_id"] == 111222333
        assert item["membership_status"] == "non_member"

    @pytest.mark.asyncio
    async def test_verification_status_unauthorized_rejected(
        self, client: AsyncClient, mock_unauthorized_session: str
    ):
        """Contract: Unauthorized users are rejected."""
        response = await client.get(
            "/api/users/search?query=123456789",
            cookies={"session": mock_unauthorized_session},
        )

        # Should reject with 400 (no authorized guilds)
        assert response.status_code == 400


@pytest.mark.contract
class TestVoiceSettingsEndpoint:
    """Contract tests for voice settings API endpoint."""

    @pytest.mark.asyncio
    async def test_voice_settings_search_returns_correct_shape(
        self, client: AsyncClient, mock_admin_session: str
    ):
        """Contract: Voice settings search returns expected payload shape."""
        response = await client.get(
            "/api/voice/search?user_id=123456789",
            cookies={"session": mock_admin_session},
        )

        assert response.status_code == 200
        data = response.json()

        # Contract: Response structure
        assert "success" in data
        assert "total" in data
        assert "items" in data

        # Contract: Item structure (when results exist)
        if data["total"] > 0:
            item = data["items"][0]
            assert "owner_id" in item
            assert "voice_channel_id" in item
            assert "is_active" in item

    @pytest.mark.asyncio
    async def test_voice_settings_by_owner(
        self, client: AsyncClient, mock_admin_session: str
    ):
        """Contract: Voice channels for owner are returned."""
        # User 123456789 is seeded with voice channels in conftest
        response = await client.get(
            "/api/voice/search?user_id=123456789",
            cookies={"session": mock_admin_session},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["total"] >= 1

        # All items should belong to the owner
        for item in data["items"]:
            assert item["owner_id"] == 123456789

    @pytest.mark.asyncio
    async def test_voice_settings_empty_for_nonexistent_user(
        self, client: AsyncClient, mock_admin_session: str
    ):
        """Contract: Nonexistent user returns empty results."""
        response = await client.get(
            "/api/voice/search?user_id=999999999999",
            cookies={"session": mock_admin_session},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["total"] == 0
        assert len(data["items"]) == 0

    @pytest.mark.asyncio
    async def test_voice_settings_moderator_access(
        self, client: AsyncClient, mock_moderator_session: str
    ):
        """Contract: Moderators can access voice settings."""
        response = await client.get(
            "/api/voice/search?user_id=123456789",
            cookies={"session": mock_moderator_session},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_voice_settings_unauthorized_rejected(
        self, client: AsyncClient, mock_unauthorized_session: str
    ):
        """Contract: Unauthorized users are rejected."""
        response = await client.get(
            "/api/voice/search?user_id=123456789",
            cookies={"session": mock_unauthorized_session},
        )

        # Should reject with 400 (no authorized guilds)
        assert response.status_code == 400


@pytest.mark.contract
class TestHealthEndpoint:
    """Contract tests for health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_liveness_returns_ok(self, client: AsyncClient):
        """Contract: Liveness endpoint returns healthy status."""
        response = await client.get("/api/health/liveness")

        assert response.status_code == 200
        data = response.json()

        assert "status" in data
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_health_readiness_returns_ok(self, client: AsyncClient):
        """Contract: Readiness endpoint returns healthy status."""
        response = await client.get("/api/health/readiness")

        assert response.status_code == 200
        data = response.json()

        assert "status" in data
        assert data["status"] == "ok"


@pytest.mark.contract
class TestApiAuthContract:
    """Contract tests for API authentication."""

    @pytest.mark.asyncio
    async def test_no_session_redirects_or_rejects(self, client: AsyncClient):
        """Contract: Request without session is handled appropriately."""
        response = await client.get("/api/users/search?query=test")

        # Should reject unauthenticated requests
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_invalid_session_rejected(self, client: AsyncClient):
        """Contract: Invalid session token is rejected."""
        response = await client.get(
            "/api/users/search?query=test",
            cookies={"session": "invalid_token_here"},
        )

        # Should reject invalid session
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_valid_admin_session_accepted(
        self, client: AsyncClient, mock_admin_session: str
    ):
        """Contract: Valid admin session is accepted."""
        response = await client.get(
            "/api/users/search?query=",
            cookies={"session": mock_admin_session},
        )

        assert response.status_code == 200
