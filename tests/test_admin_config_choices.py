"""
Unit tests for admin config choices and validation.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from cogs.admin.commands import AdminCog, ConfigSchema
from discord import app_commands


class TestConfigSchema:
    """Test cases for ConfigSchema validation and choices."""

    def test_get_key_choices(self):
        """Test that key choices are properly formatted."""
        choices = ConfigSchema.get_key_choices()

        assert isinstance(choices, list)
        assert len(choices) > 0

        # Check that all choices are properly formatted
        for choice in choices:
            assert isinstance(choice, app_commands.Choice)
            assert isinstance(choice.name, str)
            assert isinstance(choice.value, str)
            assert choice.value in ConfigSchema.ALLOWED_KEYS
            assert " - " in choice.name  # Should have description

    def test_get_type_for_key(self):
        """Test type retrieval for configuration keys."""
        assert ConfigSchema.get_type_for_key("voice.cooldown_seconds") == int
        assert ConfigSchema.get_type_for_key("features.auto_role") == bool
        assert ConfigSchema.get_type_for_key("settings.prefix") == str
        assert ConfigSchema.get_type_for_key("nonexistent.key") == str  # Default

    def test_validate_value_int_success(self):
        """Test successful integer validation."""
        is_valid, error, coerced = ConfigSchema.validate_value(
            "voice.cooldown_seconds", "120"
        )

        assert is_valid is True
        assert error == ""
        assert coerced == 120
        assert isinstance(coerced, int)

    def test_validate_value_int_range_error(self):
        """Test integer validation with range constraints."""
        # Test below minimum
        is_valid, error, coerced = ConfigSchema.validate_value(
            "voice.cooldown_seconds", "-1"
        )
        assert is_valid is False
        assert "must be at least 0" in error

        # Test above maximum
        is_valid, error, coerced = ConfigSchema.validate_value(
            "voice.cooldown_seconds", "5000"
        )
        assert is_valid is False
        assert "must be at most 3600" in error

    def test_validate_value_int_type_error(self):
        """Test integer validation with invalid type."""
        is_valid, error, coerced = ConfigSchema.validate_value(
            "voice.cooldown_seconds", "not_a_number"
        )

        assert is_valid is False
        assert "Cannot convert 'not_a_number' to int" in error

    def test_validate_value_bool_success(self):
        """Test successful boolean validation."""
        test_cases = [
            ("true", True),
            ("false", False),
            ("1", True),
            ("0", False),
            ("yes", True),
            ("no", False),
            ("enabled", True),
            ("disabled", False),
        ]

        for input_val, expected in test_cases:
            is_valid, error, coerced = ConfigSchema.validate_value(
                "features.auto_role", input_val
            )
            assert is_valid is True, f"Failed for input '{input_val}'"
            assert error == ""
            assert coerced == expected
            assert isinstance(coerced, bool)

    def test_validate_value_bool_error(self):
        """Test boolean validation with invalid values."""
        is_valid, error, coerced = ConfigSchema.validate_value(
            "features.auto_role", "maybe"
        )

        assert is_valid is False
        assert "Invalid boolean value" in error

    def test_validate_value_string_success(self):
        """Test successful string validation."""
        is_valid, error, coerced = ConfigSchema.validate_value("settings.prefix", "!")

        assert is_valid is True
        assert error == ""
        assert coerced == "!"
        assert isinstance(coerced, str)

    def test_validate_value_unknown_key(self):
        """Test validation with unknown configuration key."""
        is_valid, error, coerced = ConfigSchema.validate_value("unknown.key", "value")

        assert is_valid is False
        assert "Unknown configuration key" in error

    def test_validate_value_list_int_success(self):
        """Test successful list<int> validation."""
        is_valid, error, coerced = ConfigSchema.validate_value(
            "roles.bot_admins", "[123456789, 987654321]"
        )

        assert is_valid is True
        assert error == ""
        assert coerced == [123456789, 987654321]
        assert isinstance(coerced, list)
        assert all(isinstance(x, int) for x in coerced)

    def test_validate_value_list_int_invalid_json(self):
        """Test list<int> validation with invalid JSON."""
        is_valid, error, coerced = ConfigSchema.validate_value(
            "roles.bot_admins", "[123, invalid"
        )

        assert is_valid is False
        assert "Invalid JSON array" in error

    def test_validate_value_list_int_invalid_element(self):
        """Test list<int> validation with invalid element type."""
        is_valid, error, coerced = ConfigSchema.validate_value(
            "roles.bot_admins", '[123, "text"]'
        )

        assert is_valid is False
        assert "List contains invalid int values" in error


class TestAdminConfigCommand:
    """Test cases for the enhanced admin config command."""

    @pytest.fixture
    def mock_bot(self):
        """Mock bot with services."""
        bot = MagicMock()
        # Mock the guild config service methods. The AdminCog code awaits
        # `set` and `get`, while tests assert on `set_guild_setting`/
        # `get_guild_setting`. Create AsyncMocks for `set`/`get` and alias
        # the guild-named helpers to the same mocks so both usages work.
        set_mock = AsyncMock()
        get_mock = AsyncMock(return_value=120)

        bot.services.config.set = set_mock
        bot.services.config.get = get_mock

        # Aliases used by some tests / older API names
        bot.services.config.set_guild_setting = set_mock
        bot.services.config.get_guild_setting = get_mock
        bot.has_admin_permissions = AsyncMock(return_value=True)
        return bot

    @pytest.fixture
    def admin_cog(self, mock_bot):
        """AdminCog instance for testing."""
        return AdminCog(mock_bot)

    @pytest.fixture
    def mock_interaction(self):
        """Mock Discord interaction."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild.id = 123456789
        interaction.user.display_name = "TestUser"
        interaction.response.defer = AsyncMock()
        interaction.response.send_message = AsyncMock()
        interaction.followup.send = AsyncMock()
        return interaction

    @pytest.mark.asyncio
    async def test_set_config_valid_int_value(self, admin_cog, mock_interaction):
        """Test set_config with valid integer value."""
        # Access the callback function directly
        await admin_cog.set_config.callback(
            admin_cog, mock_interaction, key="voice.cooldown_seconds", value="120"
        )

        # Should defer the response
        mock_interaction.response.defer.assert_called_once_with(ephemeral=True)

        # Should set the config with coerced integer value
        admin_cog.bot.services.config.set_guild_setting.assert_called_once_with(
            123456789, "voice.cooldown_seconds", 120
        )

        # Should send success response
        mock_interaction.followup.send.assert_called_once()
        call_args = mock_interaction.followup.send.call_args
        assert call_args[1]["ephemeral"] is True

        # Check embed content - the embed is passed as keyword argument
        assert "embed" in call_args[1]
        embed = call_args[1]["embed"]
        assert isinstance(embed, discord.Embed)
        assert "Configuration Updated" in embed.title

    @pytest.mark.asyncio
    async def test_set_config_valid_bool_value(self, admin_cog, mock_interaction):
        """Test set_config with valid boolean value."""
        await admin_cog.set_config.callback(
            admin_cog, mock_interaction, key="features.auto_role", value="true"
        )

        # Should set the config with coerced boolean value
        admin_cog.bot.services.config.set_guild_setting.assert_called_once_with(
            123456789, "features.auto_role", True
        )

        # Should send success response
        mock_interaction.followup.send.assert_called_once()
        call_args = mock_interaction.followup.send.call_args
        assert call_args[1]["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_set_config_invalid_value(self, admin_cog, mock_interaction):
        """Test set_config with invalid value (type mismatch)."""
        await admin_cog.set_config.callback(
            admin_cog,
            mock_interaction,
            key="voice.cooldown_seconds",
            value="not_a_number",
        )

        # Should not call set_guild_setting
        admin_cog.bot.services.config.set_guild_setting.assert_not_called()

        # Should send error response
        mock_interaction.followup.send.assert_called_once()
        call_args = mock_interaction.followup.send.call_args
        assert call_args[1]["ephemeral"] is True

        # Check error message
        error_message = call_args[0][0]
        assert "❌ **Validation Error**" in error_message
        assert "Cannot convert 'not_a_number' to int" in error_message

    @pytest.mark.asyncio
    async def test_set_config_range_validation(self, admin_cog, mock_interaction):
        """Test set_config with out-of-range integer value."""
        await admin_cog.set_config.callback(
            admin_cog,
            mock_interaction,
            key="voice.cooldown_seconds",
            value="5000",  # Above max of 3600
        )

        # Should not call set_guild_setting
        admin_cog.bot.services.config.set_guild_setting.assert_not_called()

        # Should send error response with range information
        mock_interaction.followup.send.assert_called_once()
        call_args = mock_interaction.followup.send.call_args
        error_message = call_args[0][0]
        assert "must be at most 3600" in error_message

    @pytest.mark.asyncio
    async def test_set_config_permission_denied(self, admin_cog, mock_interaction):
        """Test set_config when user lacks admin permissions."""
        admin_cog.bot.has_admin_permissions = AsyncMock(return_value=False)

        await admin_cog.set_config.callback(
            admin_cog, mock_interaction, key="voice.cooldown_seconds", value="120"
        )

        # Should send permission error
        mock_interaction.response.send_message.assert_called_once_with(
            "You don't have permission to use this command.", ephemeral=True
        )

        # Should not set config
        admin_cog.bot.services.config.set_guild_setting.assert_not_called()

    @pytest.mark.asyncio
    async def test_value_autocomplete_int_suggestions(
        self, admin_cog, mock_interaction
    ):
        """Test autocomplete for integer values."""
        # Mock interaction data with selected key
        mock_interaction.data = {
            "options": [{"name": "key", "value": "voice.cooldown_seconds"}]
        }

        choices = await admin_cog.value_autocomplete(mock_interaction, "6")

        assert isinstance(choices, list)
        assert len(choices) > 0

        # Should include some numeric suggestions
        values = [choice.value for choice in choices]
        assert "60" in values  # Default value

        # Choices should be app_commands.Choice objects
        for choice in choices:
            assert isinstance(choice, app_commands.Choice)
            assert isinstance(choice.value, str)

    @pytest.mark.asyncio
    async def test_value_autocomplete_bool_suggestions(
        self, admin_cog, mock_interaction
    ):
        """Test autocomplete for boolean values."""
        mock_interaction.data = {
            "options": [{"name": "key", "value": "features.auto_role"}]
        }

        choices = await admin_cog.value_autocomplete(mock_interaction, "t")

        assert isinstance(choices, list)

        # Should include boolean suggestions
        values = [choice.value for choice in choices]
        assert "true" in values

    @pytest.mark.asyncio
    async def test_value_autocomplete_no_key_selected(
        self, admin_cog, mock_interaction
    ):
        """Test autocomplete when no key is selected."""
        mock_interaction.data = {"options": []}

        choices = await admin_cog.value_autocomplete(mock_interaction, "test")

        assert isinstance(choices, list)
        assert len(choices) == 1
        assert choices[0].name == "Select a key first"

    def test_config_schema_coverage(self):
        """Test that all defined keys have proper validation info."""
        for _key, info in ConfigSchema.ALLOWED_KEYS.items():
            assert "type" in info
            assert "description" in info
            assert info["type"] in (int, str, bool, list)
            assert isinstance(info["description"], str)
            assert len(info["description"]) > 0
