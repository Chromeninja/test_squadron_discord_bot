"""Tests for VoiceService.initialize_guild_voice_channels method."""

import logging
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from services.voice_service import VoiceService


class TestVoiceServiceInitialization:
    """Test voice service initialization functionality."""

    @pytest.fixture
    def mock_config_service(self):
        """Mock ConfigService instance."""
        config_service = AsyncMock()
        config_service.get_guild_jtc_channels = AsyncMock()
        return config_service

    @pytest.fixture
    def mock_bot(self):
        """Mock Discord bot instance."""
        bot = MagicMock()

        # Mock guild
        guild = MagicMock()
        guild.id = 12345
        guild.name = "Test Guild"
        bot.get_guild.return_value = guild

        # Mock voice channels
        voice_channel1 = MagicMock(spec=discord.VoiceChannel)
        voice_channel1.id = 111
        voice_channel2 = MagicMock(spec=discord.VoiceChannel)
        voice_channel2.id = 222

        guild.get_channel.side_effect = lambda channel_id: {
            111: voice_channel1,
            222: voice_channel2,
            999: None,  # Missing channel
        }.get(channel_id)

        return bot

    @pytest.fixture
    def voice_service(self, mock_config_service):
        """Create VoiceService instance with mocked dependencies."""
        service = VoiceService(mock_config_service)
        return service

    @pytest.mark.asyncio
    async def test_initialize_guild_voice_channels_success(
        self, voice_service, mock_config_service, mock_bot, caplog
    ):
        """Test successful initialization with valid JTC channels."""
        # Setup
        voice_service.bot = mock_bot
        mock_config_service.get_guild_jtc_channels.return_value = [111, 222]

        with caplog.at_level(logging.INFO):
            await voice_service.initialize_guild_voice_channels(12345)

        # Verify config service was called
        mock_config_service.get_guild_jtc_channels.assert_called_once_with(12345)

        # Verify bot interactions
        mock_bot.get_guild.assert_called_once_with(12345)

        # Check log messages
        log_messages = [record.message for record in caplog.records]
        assert any(
            "Initializing voice channels for guild 12345" in msg for msg in log_messages
        )
        assert any(
            "Found 2 valid JTC channels in guild Test Guild" in msg
            for msg in log_messages
        )
        assert any(
            "Voice channel initialization completed for guild Test Guild (12345)" in msg
            for msg in log_messages
        )

    @pytest.mark.asyncio
    async def test_initialize_guild_voice_channels_missing_channels(
        self, voice_service, mock_config_service, mock_bot, caplog
    ):
        """Test initialization with some missing JTC channels."""
        # Setup
        voice_service.bot = mock_bot
        mock_config_service.get_guild_jtc_channels.return_value = [
            111,
            999,
        ]  # 999 doesn't exist

        with caplog.at_level(logging.INFO):  # Capture INFO and higher levels
            await voice_service.initialize_guild_voice_channels(12345)

        # Check log messages
        log_messages = [record.message for record in caplog.records]
        assert any(
            "Found 1 valid JTC channels in guild Test Guild" in msg
            for msg in log_messages
        )
        assert any(
            "Missing 1 configured JTC channels in guild Test Guild: [999]" in msg
            for msg in log_messages
        )

    @pytest.mark.asyncio
    async def test_initialize_guild_voice_channels_no_jtc_channels(
        self, voice_service, mock_config_service, mock_bot, caplog
    ):
        """Test initialization with no configured JTC channels."""
        # Setup
        voice_service.bot = mock_bot
        mock_config_service.get_guild_jtc_channels.return_value = []

        with caplog.at_level(logging.INFO):
            await voice_service.initialize_guild_voice_channels(12345)

        # Check log messages
        log_messages = [record.message for record in caplog.records]
        assert any(
            "No JTC channels configured for guild Test Guild (12345)" in msg
            for msg in log_messages
        )

    @pytest.mark.asyncio
    async def test_initialize_guild_voice_channels_no_bot(
        self, voice_service, mock_config_service, caplog
    ):
        """Test initialization when bot instance is not available."""
        # Setup - no bot instance set
        voice_service.bot = None

        with caplog.at_level(logging.WARNING):
            await voice_service.initialize_guild_voice_channels(12345)

        # Check log messages
        log_messages = [record.message for record in caplog.records]
        assert any(
            "Bot instance not available for guild 12345 voice initialization" in msg
            for msg in log_messages
        )

        # Verify config service was not called
        mock_config_service.get_guild_jtc_channels.assert_not_called()

    @pytest.mark.asyncio
    async def test_initialize_guild_voice_channels_guild_not_found(
        self, voice_service, mock_config_service, mock_bot, caplog
    ):
        """Test initialization when guild is not found."""
        # Setup
        voice_service.bot = mock_bot
        mock_bot.get_guild.return_value = None  # Guild not found

        with caplog.at_level(logging.WARNING):
            await voice_service.initialize_guild_voice_channels(12345)

        # Check log messages
        log_messages = [record.message for record in caplog.records]
        assert any(
            "Guild 12345 not found for voice channel initialization" in msg
            for msg in log_messages
        )

        # Verify config service was not called
        mock_config_service.get_guild_jtc_channels.assert_not_called()

    @pytest.mark.asyncio
    async def test_initialize_guild_voice_channels_exception_handling(
        self, voice_service, mock_config_service, mock_bot, caplog
    ):
        """Test exception handling during initialization."""
        # Setup
        voice_service.bot = mock_bot
        mock_config_service.get_guild_jtc_channels.side_effect = Exception(
            "Config error"
        )

        with caplog.at_level(
            logging.INFO
        ):  # Capture INFO and higher to get both ERROR and INFO messages
            await voice_service.initialize_guild_voice_channels(12345)

        # Check log messages
        log_messages = [record.message for record in caplog.records]
        # The exception is caught in _get_guild_jtc_channels, so we expect that error message
        assert any("Error getting JTC channels" in msg for msg in log_messages)
        # And the main flow should continue with empty list
        assert any(
            "No JTC channels configured for guild Test Guild (12345)" in msg
            for msg in log_messages
        )
