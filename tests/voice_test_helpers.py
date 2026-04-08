"""Shared voice test doubles and setup helpers."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

from services.config_service import ConfigService
from services.voice_service import VoiceService


class MockVoiceChannel:
    """Mock Discord voice channel."""

    def __init__(
        self,
        channel_id: int,
        name: str = "test-channel",
        members: list[Any] | None = None,
        category: Any | None = None,
        guild: Any | None = None,
    ) -> None:
        self.id = channel_id
        self.name = name
        self.members = members or []
        self.category = category or MagicMock()
        self.guild = guild or MagicMock()
        self.guild.id = getattr(self.guild, "id", 12345)
        if not hasattr(self.guild, "get_member"):
            self.guild.get_member = MagicMock(return_value=None)
        self.category.id = getattr(self.category, "id", 77777)
        self.category.name = getattr(self.category, "name", "Voice Category")
        if not hasattr(self.category, "create_voice_channel"):
            self.category.create_voice_channel = AsyncMock()
        self.user_limit = 0
        self.bitrate = 64000
        self.overwrites: dict[Any, Any] = {}
        self.mention = f"<#{channel_id}>"

    async def delete(self, reason: str | None = None) -> None:
        """Mock channel deletion."""

    async def edit(self, **kwargs: Any) -> None:
        """Mock channel edit operation."""
        overwrites = kwargs.get("overwrites")
        if overwrites is not None:
            self.overwrites = overwrites
        for key, value in kwargs.items():
            if key != "overwrites" and hasattr(self, key):
                setattr(self, key, value)

    async def __aenter__(self) -> MockVoiceChannel:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        return None


class MockMember:
    """Mock Discord member."""

    def __init__(self, user_id: int, display_name: str = "TestUser") -> None:
        self.id = user_id
        self.display_name = display_name
        self.mention = f"<@{user_id}>"
        self.voice = MagicMock()
        self.voice.channel = None
        self.top_role = MagicMock()
        self.top_role.name = "member"

    async def move_to(self, channel: Any) -> None:
        """Mock member move."""

    async def send(self, message: str) -> None:
        """Mock sending DM to member."""


class MockGuild:
    """Mock Discord guild."""

    def __init__(self, guild_id: int = 12345) -> None:
        self.id = guild_id
        self.name = "Test Guild"
        self.voice_channels: list[MockVoiceChannel] = []

    def get_channel(self, channel_id: int) -> MockVoiceChannel | None:
        """Mock get_channel method."""
        for channel in self.voice_channels:
            if channel.id == channel_id:
                return channel
        return None

    def get_member(self, user_id: int) -> None:
        """Mock get_member method."""
        return None

    async def create_voice_channel(
        self,
        name: str,
        category: Any = None,
        **kwargs: Any,
    ) -> MockVoiceChannel:
        """Mock voice channel creation."""
        return MockVoiceChannel(channel_id=99999, name=name, category=category)


class MockBot:
    """Mock Discord bot."""

    def __init__(self) -> None:
        self._channels: dict[int, MockVoiceChannel] = {}
        self.guilds: list[Any] = []
        self.user = MagicMock()
        self.user.id = 12345

    async def wait_until_ready(self) -> None:
        """Mock wait_until_ready method."""

    def get_guild(self, guild_id: int) -> None:
        """Get mock guild by ID."""
        return None

    def get_channel(self, channel_id: int) -> MockVoiceChannel | None:
        """Get mock channel by ID."""
        return self._channels.get(channel_id)

    async def fetch_channel(self, channel_id: int) -> MockVoiceChannel | None:
        """Fetch mock channel by ID."""
        return self._channels.get(channel_id)

    def add_channel(self, channel: MockVoiceChannel) -> None:
        """Add mock channel."""
        self._channels[channel.id] = channel

    def remove_channel(self, channel_id: int) -> None:
        """Remove mock channel."""
        self._channels.pop(channel_id, None)


async def create_voice_service_with_bot(
    *,
    test_mode: bool = False,
) -> tuple[VoiceService, MockBot, ConfigService]:
    """Create a voice service with a shared mock bot."""
    config_service = ConfigService()
    await config_service.initialize()

    mock_bot = MockBot()
    voice_service = VoiceService(
        config_service,
        bot=cast(Any, mock_bot),
        test_mode=test_mode,
    )
    await voice_service.initialize()
    return voice_service, mock_bot, config_service


async def shutdown_voice_service_with_bot(
    voice_service: VoiceService,
    config_service: ConfigService,
) -> None:
    """Shut down shared voice service resources."""
    await voice_service.shutdown()
    await config_service.shutdown()