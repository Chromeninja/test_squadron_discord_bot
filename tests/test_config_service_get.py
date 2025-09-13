"""
Unit tests for ConfigService.get method.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from services.config_service import ConfigService


@pytest.fixture
def config_service():
    """ConfigService instance with mocked dependencies."""
    service = ConfigService()
    service._initialized = True  # Skip initialization
    service._global_config = {
        "voice": {"cooldown_seconds": "300", "user_limit": "5"},
        "test": {"nested": {"value": "global_default"}},
    }
    return service


class TestConfigServiceGet:
    """Test cases for ConfigService.get method."""

    @pytest.mark.asyncio
    async def test_get_with_parser_success(self, config_service):
        """Test get method with parser converting string to int."""
        # Mock _get_guild_settings to return guild-specific settings
        config_service._get_guild_settings = AsyncMock(
            return_value={"voice": {"cooldown_seconds": "120"}}
        )

        result = await config_service.get(
            guild_id=123, key="voice.cooldown_seconds", parser=int
        )

        assert result == 120
        assert isinstance(result, int)

    @pytest.mark.asyncio
    async def test_get_with_parser_invalid_value(self, config_service):
        """Test get method with parser when value cannot be parsed."""
        # Mock guild settings to return an invalid string for int parsing
        config_service._get_guild_settings = AsyncMock(
            return_value={"voice": {"cooldown_seconds": "invalid_number"}}
        )

        result = await config_service.get(
            guild_id=123, key="voice.cooldown_seconds", default=60, parser=int
        )

        # Should return default when parsing fails
        assert result == 60

    @pytest.mark.asyncio
    async def test_get_without_parser(self, config_service):
        """Test get method without parser (returns raw value)."""
        config_service._get_guild_settings = AsyncMock(
            return_value={"test": {"setting": "raw_value"}}
        )

        result = await config_service.get(guild_id=123, key="test.setting")

        assert result == "raw_value"

    @pytest.mark.asyncio
    async def test_get_falls_back_to_global_with_parser(self, config_service):
        """Test get method falls back to global config and applies parser."""
        # No guild-specific setting, should use global config
        config_service._get_guild_settings = AsyncMock(return_value={})

        result = await config_service.get(
            guild_id=123, key="voice.cooldown_seconds", parser=int
        )

        # Should parse global config value "300" to int 300
        assert result == 300
        assert isinstance(result, int)

    @pytest.mark.asyncio
    async def test_get_with_default_when_not_found(self, config_service):
        """Test get method returns default when key not found anywhere."""
        config_service._get_guild_settings = AsyncMock(return_value={})

        result = await config_service.get(
            guild_id=123, key="non.existent.key", default="default_value", parser=str
        )

        assert result == "default_value"

    @pytest.mark.asyncio
    async def test_get_parser_not_applied_to_default(self, config_service):
        """Test that parser is not applied when returning default value."""
        config_service._get_guild_settings = AsyncMock(return_value={})

        # Default is already the correct type, parser should not be applied
        result = await config_service.get(
            guild_id=123,
            key="non.existent.key",
            default=42,  # Already an int
            parser=int,
        )

        assert result == 42
        assert isinstance(result, int)

    @pytest.mark.asyncio
    async def test_get_with_float_parser(self, config_service):
        """Test get method with float parser."""
        config_service._get_guild_settings = AsyncMock(
            return_value={"test": {"float_value": "3.14"}}
        )

        result = await config_service.get(
            guild_id=123, key="test.float_value", parser=float
        )

        assert result == 3.14
        assert isinstance(result, float)

    @pytest.mark.asyncio
    async def test_get_with_bool_parser(self, config_service):
        """Test get method with bool parser."""
        config_service._get_guild_settings = AsyncMock(
            return_value={"test": {"enabled": "true"}}
        )

        result = await config_service.get(guild_id=123, key="test.enabled", parser=bool)

        # Note: bool("true") is True, but bool("false") is also True
        # This test demonstrates the parser behavior
        assert result is True

    @pytest.mark.asyncio
    async def test_get_delegates_to_get_guild_setting(self, config_service):
        """Test that get method properly delegates to get_guild_setting."""
        # Mock get_guild_setting to verify it's called correctly
        config_service.get_guild_setting = AsyncMock(return_value="test_value")

        result = await config_service.get(
            guild_id=456, key="test.key", default="default"
        )

        # Verify get_guild_setting was called with correct parameters
        config_service.get_guild_setting.assert_called_once_with(
            456, "test.key", "default"
        )
        assert result == "test_value"

    @pytest.mark.asyncio
    async def test_get_logs_parser_errors(self, config_service):
        """Test that parser errors are properly logged."""
        config_service._get_guild_settings = AsyncMock(
            return_value={"test": {"value": "not_a_number"}}
        )

        # Mock the logger to verify warning is logged
        config_service.logger = Mock()

        result = await config_service.get(
            guild_id=123, key="test.value", default=0, parser=int
        )

        # Should return default and log warning
        assert result == 0
        config_service.logger.warning.assert_called_once()

        # Check that the warning message contains expected information
        warning_call = config_service.logger.warning.call_args[0][0]
        assert "Failed to parse config value" in warning_call
        assert "not_a_number" in warning_call
        assert "test.value" in warning_call

    @pytest.mark.asyncio
    async def test_get_handles_none_value_with_parser(self, config_service):
        """Test that None values are handled correctly with parser."""
        config_service._get_guild_settings = AsyncMock(return_value={})
        config_service._global_config = {}  # No global config either

        result = await config_service.get(
            guild_id=123, key="non.existent", default=None, parser=int
        )

        # Parser should not be applied to None value
        assert result is None

    @pytest.mark.asyncio
    async def test_get_direct_key_match(self, config_service):
        """Test get method with direct key match (non-nested)."""
        config_service._get_guild_settings = AsyncMock(
            return_value={"simple_key": "direct_value"}
        )

        result = await config_service.get(guild_id=123, key="simple_key")

        assert result == "direct_value"

    @pytest.mark.asyncio
    async def test_get_nested_key_fallback_to_global(self, config_service):
        """Test get method falls back to global config for nested keys."""
        config_service._get_guild_settings = AsyncMock(return_value={})

        result = await config_service.get(
            guild_id=123, key="test.nested.value", parser=str
        )

        # Should find "global_default" from the global config
        assert result == "global_default"
