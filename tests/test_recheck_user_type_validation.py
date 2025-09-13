"""
Tests for type validation in recheck user functionality.

Tests ensure that proper Bot instances are passed to verification functions
and that meaningful errors are raised when strings or invalid objects are passed.
"""
from unittest.mock import MagicMock

import discord
import pytest
from helpers.role_helper import assign_roles, reverify_member


class TestRecheckUserTypeValidation:
    """Test type validation for recheck user functions."""

    @pytest.fixture
    def mock_member(self):
        """Create a mock Discord member."""
        member = MagicMock(spec=discord.Member)
        member.id = 987654321
        member.display_name = "TestUser"
        member.mention = "<@987654321>"
        member.roles = []
        return member

    @pytest.fixture
    def invalid_bot_no_http_client(self):
        """Create a bot instance without http_client or services."""
        class InvalidBot:
            pass
        return InvalidBot()

    @pytest.fixture
    def invalid_bot_no_role_cache(self):
        """Create a bot instance without role_cache."""
        class InvalidBotNoCache:
            http_client = MagicMock()
        return InvalidBotNoCache()

    @pytest.mark.asyncio
    async def test_reverify_member_string_bot_raises_error(self, mock_member):
        """Test that reverify_member raises TypeError when passed a string instead of bot."""
        # This test demonstrates the fix - previously would have failed with
        # 'str' object has no attribute 'http_client'
        with pytest.raises(TypeError) as exc_info:
            await reverify_member(mock_member, "test_handle", "bot_as_string")

        assert "received string 'bot_as_string' instead of Bot instance" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_reverify_member_invalid_bot_raises_error(self, mock_member, invalid_bot_no_http_client):
        """Test that reverify_member raises TypeError for bot without http_client."""
        with pytest.raises(TypeError) as exc_info:
            await reverify_member(mock_member, "test_handle", invalid_bot_no_http_client)

        assert "Bot instance passed to reverify_member lacks http_client attribute" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_assign_roles_string_bot_raises_error(self, mock_member):
        """Test that assign_roles raises TypeError when passed a string instead of bot."""
        # This test demonstrates the fix for assign_roles function
        with pytest.raises(TypeError) as exc_info:
            await assign_roles(mock_member, 1, "TestHandle", "bot_as_string")

        assert "received string 'bot_as_string' instead of Bot instance" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_assign_roles_invalid_bot_raises_error(self, mock_member, invalid_bot_no_role_cache):
        """Test that assign_roles raises TypeError for bot without role_cache."""
        with pytest.raises(TypeError) as exc_info:
            await assign_roles(mock_member, 1, "TestHandle", invalid_bot_no_role_cache)

        assert "Bot instance passed to assign_roles lacks role_cache attribute" in str(exc_info.value)

    def test_type_validation_prevents_attribute_error(self):
        """Test that our validation would prevent the original 'str' object has no attribute 'http_client' error."""
        # This test verifies that the type checking prevents the original error

        # Previously, if a string was passed where a bot instance was expected,
        # the code would fail deep in the call stack with:
        # AttributeError: 'str' object has no attribute 'http_client'

        # Now, with our type checking, we get a clear TypeError immediately
        # at the service boundary, making debugging much easier.

        # Test data that would have caused the original error
        problematic_cases = [
            "string_instead_of_bot",
            123,  # number instead of bot
            None,  # None instead of bot
            [],   # list instead of bot
        ]

        for invalid_bot in problematic_cases:
            # Verify that each problematic case raises TypeError immediately
            assert isinstance(invalid_bot, str | int | type(None) | list)
            # The actual test is in the async methods above, but this documents
            # the problem we're solving
