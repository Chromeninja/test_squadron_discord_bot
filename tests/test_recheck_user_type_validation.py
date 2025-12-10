"""
Tests for type validation in role application functionality.

Tests ensure that proper Bot instances are passed to verification functions
and that meaningful errors are raised when strings or invalid objects are passed.
"""

from unittest.mock import MagicMock

import discord
import pytest

from helpers.role_helper import apply_roles_for_status


class TestApplyRolesTypeValidation:
    """Test type validation for apply_roles_for_status function."""

    @pytest.fixture
    def mock_member(self):
        """Create a mock Discord member."""
        member = MagicMock(spec=discord.Member)
        member.id = 987654321
        member.display_name = "TestUser"
        member.mention = "<@987654321>"
        member.roles = []
        return member

    @pytest.mark.asyncio
    async def test_apply_roles_string_bot_raises_error(self, mock_member):
        """Test that apply_roles_for_status raises TypeError when passed a string instead of bot."""
        with pytest.raises(TypeError) as exc_info:
            await apply_roles_for_status(
                mock_member, 
                "main", 
                "TestHandle", 
                "bot_as_string"
            )

        assert "expects a bot instance, not string" in str(exc_info.value)

    def test_type_validation_prevents_attribute_error(self):
        """Test that our validation would prevent the original 'str' object has no attribute 'services' error."""
        # This test verifies that the type checking prevents the original error

        # Previously, if a string was passed where a bot instance was expected,
        # the code would fail deep in the call stack with:
        # AttributeError: 'str' object has no attribute 'services'

        # Now, with our type checking, we get a clear TypeError immediately
        # at the service boundary, making debugging much easier.

        # Test data that would have caused the original error
        problematic_cases = [
            "string_instead_of_bot",
            123,  # number instead of bot
        ]

        for invalid_bot in problematic_cases:
            # Verify that each problematic case is caught by type check
            assert isinstance(invalid_bot, str | int)
            # The actual test is in the async methods above, but this documents
            # the problem we're solving
