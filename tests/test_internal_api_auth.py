"""
Tests for internal API authentication and security behavior.

These tests verify that:
1. Internal API requires authentication for protected endpoints
2. API key validation works correctly
3. Production mode fails closed without API key
4. Dev/test mode allows unauthenticated access (with warning)
"""

from unittest.mock import MagicMock

import pytest

from services.internal_api import InternalAPIServer


class TestInternalAPIAuthentication:
    """Tests for internal API authentication behavior."""

    @pytest.fixture
    def mock_services(self):
        """Create a minimal mock services container."""
        services = MagicMock()
        services.bot = MagicMock()
        services.health = MagicMock()
        services.config = MagicMock()
        return services

    def test_production_requires_api_key(self, mock_services, monkeypatch):
        """Test that production mode fails closed without API key."""
        # Clear any existing env vars
        monkeypatch.delenv("INTERNAL_API_KEY", raising=False)
        monkeypatch.delenv("ENV", raising=False)

        # Should raise RuntimeError in production without API key
        exc_info = pytest.raises(RuntimeError, InternalAPIServer, mock_services)

        assert "INTERNAL_API_KEY must be set in production" in str(exc_info.value)

    def test_dev_mode_allows_no_api_key(self, mock_services, monkeypatch):
        """Test that dev mode auto-generates a key when INTERNAL_API_KEY is not set."""
        monkeypatch.delenv("INTERNAL_API_KEY", raising=False)
        monkeypatch.setenv("ENV", "dev")

        # Should not raise in dev mode — auto-generates a key
        server = InternalAPIServer(mock_services)
        assert server.api_key != ""
        assert len(server.api_key) > 0

    def test_test_mode_allows_no_api_key(self, mock_services, monkeypatch):
        """Test that test mode auto-generates a key when INTERNAL_API_KEY is not set."""
        monkeypatch.delenv("INTERNAL_API_KEY", raising=False)
        monkeypatch.setenv("ENV", "test")

        # Should not raise in test mode — auto-generates a key
        server = InternalAPIServer(mock_services)
        assert server.api_key != ""
        assert len(server.api_key) > 0

    def test_api_key_loaded_from_env(self, mock_services, monkeypatch):
        """Test that API key is correctly loaded from environment."""
        test_key = "test_secret_key_12345"
        monkeypatch.setenv("INTERNAL_API_KEY", test_key)
        monkeypatch.setenv("ENV", "dev")  # Avoid production check

        server = InternalAPIServer(mock_services)
        assert server.api_key == test_key

    def test_check_auth_with_valid_key(self, mock_services, monkeypatch):
        """Test that _check_auth returns True for valid Bearer token."""
        test_key = "valid_api_key"
        monkeypatch.setenv("INTERNAL_API_KEY", test_key)
        monkeypatch.setenv("ENV", "dev")

        server = InternalAPIServer(mock_services)

        # Create mock request with valid Authorization header
        mock_request = MagicMock()
        mock_request.headers = {"Authorization": f"Bearer {test_key}"}

        assert server._check_auth(mock_request) is True

    def test_check_auth_with_invalid_key(self, mock_services, monkeypatch):
        """Test that _check_auth returns False for invalid Bearer token."""
        test_key = "valid_api_key"
        monkeypatch.setenv("INTERNAL_API_KEY", test_key)
        monkeypatch.setenv("ENV", "dev")

        server = InternalAPIServer(mock_services)

        # Create mock request with invalid Authorization header
        mock_request = MagicMock()
        mock_request.headers = {"Authorization": "Bearer wrong_key"}

        assert server._check_auth(mock_request) is False

    def test_check_auth_missing_header(self, mock_services, monkeypatch):
        """Test that _check_auth returns False when Authorization header is missing."""
        test_key = "valid_api_key"
        monkeypatch.setenv("INTERNAL_API_KEY", test_key)
        monkeypatch.setenv("ENV", "dev")

        server = InternalAPIServer(mock_services)

        # Create mock request without Authorization header
        mock_request = MagicMock()
        mock_request.headers = {}

        assert server._check_auth(mock_request) is False

    def test_check_auth_wrong_scheme(self, mock_services, monkeypatch):
        """Test that _check_auth returns False for non-Bearer auth scheme."""
        test_key = "valid_api_key"
        monkeypatch.setenv("INTERNAL_API_KEY", test_key)
        monkeypatch.setenv("ENV", "dev")

        server = InternalAPIServer(mock_services)

        # Create mock request with Basic auth instead of Bearer
        mock_request = MagicMock()
        mock_request.headers = {"Authorization": f"Basic {test_key}"}

        assert server._check_auth(mock_request) is False

    def test_check_auth_requires_key_even_when_auto_generated(
        self, mock_services, monkeypatch
    ):
        """Test that _check_auth requires the auto-generated key in dev mode."""
        monkeypatch.delenv("INTERNAL_API_KEY", raising=False)
        monkeypatch.setenv("ENV", "dev")

        server = InternalAPIServer(mock_services)

        # Request without header should be rejected even with auto-gen key
        mock_request = MagicMock()
        mock_request.headers = {}
        assert server._check_auth(mock_request) is False

        # Request with correct auto-gen key should succeed
        mock_request_valid = MagicMock()
        mock_request_valid.headers = {
            "Authorization": f"Bearer {server.api_key}"
        }
        assert server._check_auth(mock_request_valid) is True

    def test_host_and_port_configuration(self, mock_services, monkeypatch):
        """Test that host and port can be configured via environment."""
        monkeypatch.setenv("INTERNAL_API_HOST", "0.0.0.0")  # noqa: S104
        monkeypatch.setenv("INTERNAL_API_PORT", "9999")
        monkeypatch.setenv("INTERNAL_API_KEY", "test_key")
        monkeypatch.setenv("ENV", "dev")

        server = InternalAPIServer(mock_services)

        assert server.host == "0.0.0.0"  # noqa: S104
        assert server.port == 9999

    def test_default_host_and_port(self, mock_services, monkeypatch):
        """Test default host (127.0.0.1) and port (8082) values."""
        monkeypatch.delenv("INTERNAL_API_HOST", raising=False)
        monkeypatch.delenv("INTERNAL_API_PORT", raising=False)
        monkeypatch.setenv("INTERNAL_API_KEY", "test_key")
        monkeypatch.setenv("ENV", "dev")

        server = InternalAPIServer(mock_services)

        assert server.host == "127.0.0.1"
        assert server.port == 8082


class TestParseUserIds:
    """Tests for InternalAPIServer._parse_user_ids static method."""

    @staticmethod
    def _make_request(query_string: str = ""):
        """Build a minimal mock request with query params."""
        from unittest.mock import MagicMock

        request = MagicMock()
        # aiohttp stores query as a MultiDict; for our static method we just
        # need .query.get() to work.
        parsed = {}
        for pair in query_string.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                parsed[k] = v
        request.query = parsed
        return request

    def test_absent_param_returns_none(self) -> None:
        """No user_ids param → None (no filter)."""
        req = self._make_request("")
        assert InternalAPIServer._parse_user_ids(req) is None

    def test_valid_csv(self) -> None:
        """Comma-separated integers are parsed correctly."""
        req = self._make_request("user_ids=1,2,3")
        assert InternalAPIServer._parse_user_ids(req) == [1, 2, 3]

    def test_single_id(self) -> None:
        """A single user ID is returned as a one-element list."""
        req = self._make_request("user_ids=42")
        assert InternalAPIServer._parse_user_ids(req) == [42]

    def test_malformed_raises_400(self) -> None:
        """Non-numeric user_ids raise an HTTP 400 error."""
        from aiohttp.web import HTTPBadRequest

        req = self._make_request("user_ids=abc,def")
        pytest.raises(HTTPBadRequest, InternalAPIServer._parse_user_ids, req)

    def test_mixed_valid_invalid_raises_400(self) -> None:
        """Even one non-numeric value in user_ids raises HTTP 400."""
        from aiohttp.web import HTTPBadRequest

        req = self._make_request("user_ids=1,bad,3")
        pytest.raises(HTTPBadRequest, InternalAPIServer._parse_user_ids, req)

    def test_empty_string_returns_none(self) -> None:
        """Empty user_ids param → None."""
        req = self._make_request("user_ids=")
        assert InternalAPIServer._parse_user_ids(req) is None
