"""
Discord Mock Factories

Provides factory functions and fake classes for Discord objects.
Use these to create consistent, configurable test doubles without hitting Discord's API.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock


class FakeUser:
    """Fake Discord User for testing."""

    def __init__(
        self,
        user_id: int = 123456789,
        name: str = "TestUser",
        display_name: str | None = None,
        discriminator: str = "0",
        bot: bool = False,
        avatar: str | None = None,
    ) -> None:
        self.id = user_id
        self.name = name
        self.display_name = display_name or name
        self.discriminator = discriminator
        self.bot = bot
        self.avatar = avatar
        self.mention = f"<@{user_id}>"
        self.global_name = display_name or name
        self._dm_messages: list[Any] = []

    async def send(self, content: str | None = None, **kwargs: Any) -> None:
        """Mock DM send - stores messages for assertion."""
        self._dm_messages.append({"content": content, **kwargs})

    def __repr__(self) -> str:
        return f"<FakeUser id={self.id} name={self.name!r}>"


class FakeRole:
    """Fake Discord Role for testing."""

    def __init__(
        self,
        role_id: int = 999111222,
        name: str = "TestRole",
        position: int = 1,
        permissions: int = 0,
        mentionable: bool = False,
        hoist: bool = False,
        color: int = 0,
    ) -> None:
        self.id = role_id
        self.name = name
        self.position = position
        self.permissions = SimpleNamespace(value=permissions)
        self.mentionable = mentionable
        self.hoist = hoist
        self.color = SimpleNamespace(value=color)
        self.mention = f"<@&{role_id}>"

    def __repr__(self) -> str:
        return f"<FakeRole id={self.id} name={self.name!r}>"


class FakeMember(FakeUser):
    """Fake Discord Member (User in a Guild context) for testing."""

    def __init__(
        self,
        user_id: int = 123456789,
        name: str = "TestMember",
        display_name: str | None = None,
        nick: str | None = None,
        roles: list[FakeRole] | None = None,
        guild: FakeGuild | None = None,
        voice: FakeVoiceState | None = None,
        joined_at: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(user_id=user_id, name=name, display_name=display_name or nick or name, **kwargs)
        self.nick = nick
        self.roles = roles or []
        self.guild = guild
        self.voice = voice
        self.joined_at = joined_at
        self._added_roles: list[FakeRole] = []
        self._removed_roles: list[FakeRole] = []

    async def add_roles(self, *roles: FakeRole, reason: str | None = None) -> None:
        """Mock adding roles - tracks for assertion."""
        self._added_roles.extend(roles)
        self.roles.extend(roles)

    async def remove_roles(self, *roles: FakeRole, reason: str | None = None) -> None:
        """Mock removing roles - tracks for assertion."""
        self._removed_roles.extend(roles)
        for r in roles:
            if r in self.roles:
                self.roles.remove(r)

    async def edit(self, **kwargs: Any) -> None:
        """Mock member edit."""
        if "nick" in kwargs:
            self.nick = kwargs["nick"]
            self.display_name = kwargs["nick"] or self.name

    def __repr__(self) -> str:
        return f"<FakeMember id={self.id} name={self.name!r} guild={getattr(self.guild, 'id', None)}>"


class FakeChannel:
    """Fake Discord TextChannel for testing."""

    def __init__(
        self,
        channel_id: int = 111222333,
        name: str = "test-channel",
        guild: FakeGuild | None = None,
        category_id: int | None = None,
        position: int = 0,
    ) -> None:
        self.id = channel_id
        self.name = name
        self.guild = guild
        self.category_id = category_id
        self.position = position
        self.mention = f"<#{channel_id}>"
        self._sent_messages: list[Any] = []

    async def send(self, content: str | None = None, **kwargs: Any) -> MagicMock:
        """Mock channel send - stores messages for assertion."""
        msg = MagicMock()
        msg.content = content
        msg.id = len(self._sent_messages) + 1
        self._sent_messages.append({"content": content, **kwargs})
        return msg

    def __repr__(self) -> str:
        return f"<FakeChannel id={self.id} name={self.name!r}>"


class FakeVoiceChannel:
    """Fake Discord VoiceChannel for testing."""

    def __init__(
        self,
        channel_id: int = 444555666,
        name: str = "Test Voice",
        guild: FakeGuild | None = None,
        category_id: int | None = None,
        user_limit: int = 0,
        bitrate: int = 64000,
        members: list[FakeMember] | None = None,
    ) -> None:
        self.id = channel_id
        self.name = name
        self.guild = guild
        self.category_id = category_id
        self.user_limit = user_limit
        self.bitrate = bitrate
        self.members = members or []
        self.mention = f"<#{channel_id}>"
        self._deleted = False

    async def delete(self, reason: str | None = None) -> None:
        """Mock channel deletion."""
        self._deleted = True

    async def edit(self, **kwargs: Any) -> None:
        """Mock channel edit."""
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)

    def __repr__(self) -> str:
        return f"<FakeVoiceChannel id={self.id} name={self.name!r}>"


class FakeVoiceState:
    """Fake Discord VoiceState for testing."""

    def __init__(
        self,
        channel: FakeVoiceChannel | None = None,
        self_deaf: bool = False,
        self_mute: bool = False,
        deaf: bool = False,
        mute: bool = False,
    ) -> None:
        self.channel = channel
        self.self_deaf = self_deaf
        self.self_mute = self_mute
        self.deaf = deaf
        self.mute = mute


class FakeGuild:
    """Fake Discord Guild for testing."""

    def __init__(
        self,
        guild_id: int = 987654321,
        name: str = "Test Guild",
        owner_id: int = 123456789,
        roles: list[FakeRole] | None = None,
        channels: list[FakeChannel | FakeVoiceChannel] | None = None,
        members: list[FakeMember] | None = None,
        member_count: int | None = None,
    ) -> None:
        self.id = guild_id
        self.name = name
        self.owner_id = owner_id
        self.roles = roles or [FakeRole(guild_id, "@everyone", position=0)]
        self.channels = channels or []
        self._members = members or []
        self.member_count = member_count or len(self._members)
        self.icon = None

    @property
    def members(self) -> list[FakeMember]:
        return self._members

    def get_member(self, user_id: int) -> FakeMember | None:
        """Get member by ID."""
        for m in self._members:
            if m.id == user_id:
                return m
        return None

    def get_channel(self, channel_id: int) -> FakeChannel | FakeVoiceChannel | None:
        """Get channel by ID."""
        for c in self.channels:
            if c.id == channel_id:
                return c
        return None

    def get_role(self, role_id: int) -> FakeRole | None:
        """Get role by ID."""
        for r in self.roles:
            if r.id == role_id:
                return r
        return None

    async def fetch_member(self, user_id: int) -> FakeMember:
        """Mock fetch_member."""
        member = self.get_member(user_id)
        if not member:
            raise Exception(f"Member {user_id} not found")
        return member

    def __repr__(self) -> str:
        return f"<FakeGuild id={self.id} name={self.name!r}>"


class FakeResponse:
    """Fake Interaction Response for testing."""

    def __init__(self) -> None:
        self._is_done = False
        self.sent_modal: Any = None
        self._deferred = False
        self._messages: list[dict[str, Any]] = []

    def is_done(self) -> bool:
        return self._is_done

    async def send_message(
        self, content: str | None = None, ephemeral: bool = False, **kwargs: Any
    ) -> None:
        self._is_done = True
        self._messages.append({"content": content, "ephemeral": ephemeral, **kwargs})

    async def defer(self, ephemeral: bool = False, thinking: bool = False) -> None:
        self._is_done = True
        self._deferred = True

    async def send_modal(self, modal: Any) -> None:
        self._is_done = True
        self.sent_modal = modal


class FakeFollowup:
    """Fake Interaction Followup for testing."""

    def __init__(self) -> None:
        self._messages: list[dict[str, Any]] = []

    async def send(
        self, content: str | None = None, ephemeral: bool = False, **kwargs: Any
    ) -> MagicMock:
        msg = MagicMock()
        msg.content = content
        msg.id = len(self._messages) + 1
        self._messages.append({"content": content, "ephemeral": ephemeral, **kwargs})
        return msg


class FakeInteraction:
    """Fake Discord Interaction for testing slash commands."""

    # Explicit type annotation to allow None
    guild: FakeGuild | None

    def __init__(
        self,
        user: FakeMember | FakeUser | None = None,
        guild: FakeGuild | None = None,
        channel: FakeChannel | None = None,
        guild_id: int | None = None,
        no_guild: bool = False,
    ) -> None:
        self.user = user or FakeMember()
        # Allow explicit None for guild when no_guild=True
        if no_guild:
            self.guild = None
        else:
            self.guild = guild if guild is not None else FakeGuild()
        self.guild_id = guild_id or (self.guild.id if self.guild else None)
        self.channel = channel or FakeChannel(guild=self.guild)
        self.channel_id = self.channel.id if self.channel else None
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.locale = "en-US"
        self.command = SimpleNamespace(name="test_command")

        # Message for edit operations
        self.message = SimpleNamespace(edit=AsyncMock())

    @property
    def responded(self) -> bool:
        return self.response.is_done()


class FakeBot:
    """Fake Discord Bot for testing cogs."""

    def __init__(
        self,
        guilds: list[FakeGuild] | None = None,
        user: FakeUser | None = None,
    ) -> None:
        self.guilds = guilds or []
        self.user = user or FakeUser(user_id=1, name="TestBot", bot=True)
        self.uptime = "1h 30m"
        self._cogs: dict[str, Any] = {}
        self.services: Any = None
        self._ready = True
        self.latency = 0.05  # 50ms

    def get_cog(self, name: str) -> Any:
        return self._cogs.get(name)

    def add_cog(self, cog: Any, name: str | None = None) -> None:
        cog_name = name or cog.__class__.__name__
        self._cogs[cog_name] = cog

    def get_guild(self, guild_id: int) -> FakeGuild | None:
        for g in self.guilds:
            if g.id == guild_id:
                return g
        return None

    async def wait_until_ready(self) -> None:
        """Mock wait_until_ready."""
        pass

    async def has_admin_permissions(self, member: FakeMember) -> bool:
        """Mock admin permission check - override in tests as needed."""
        return True


# Factory functions for convenient creation


def make_user(
    user_id: int = 123456789,
    name: str = "TestUser",
    **kwargs: Any,
) -> FakeUser:
    """Create a FakeUser with defaults."""
    return FakeUser(user_id=user_id, name=name, **kwargs)


def make_role(
    role_id: int = 999111222,
    name: str = "TestRole",
    **kwargs: Any,
) -> FakeRole:
    """Create a FakeRole with defaults."""
    return FakeRole(role_id=role_id, name=name, **kwargs)


def make_member(
    user_id: int = 123456789,
    name: str = "TestMember",
    roles: list[FakeRole] | None = None,
    guild: FakeGuild | None = None,
    **kwargs: Any,
) -> FakeMember:
    """Create a FakeMember with defaults."""
    return FakeMember(user_id=user_id, name=name, roles=roles or [], guild=guild, **kwargs)


def make_channel(
    channel_id: int = 111222333,
    name: str = "test-channel",
    guild: FakeGuild | None = None,
    **kwargs: Any,
) -> FakeChannel:
    """Create a FakeChannel with defaults."""
    return FakeChannel(channel_id=channel_id, name=name, guild=guild, **kwargs)


def make_voice_channel(
    channel_id: int = 444555666,
    name: str = "Test Voice",
    guild: FakeGuild | None = None,
    members: list[FakeMember] | None = None,
    **kwargs: Any,
) -> FakeVoiceChannel:
    """Create a FakeVoiceChannel with defaults."""
    return FakeVoiceChannel(channel_id=channel_id, name=name, guild=guild, members=members, **kwargs)


def make_voice_state(
    channel: FakeVoiceChannel | None = None,
    **kwargs: Any,
) -> FakeVoiceState:
    """Create a FakeVoiceState with defaults."""
    return FakeVoiceState(channel=channel, **kwargs)


def make_guild(
    guild_id: int = 987654321,
    name: str = "Test Guild",
    roles: list[FakeRole] | None = None,
    members: list[FakeMember] | None = None,
    channels: list[FakeChannel | FakeVoiceChannel] | None = None,
    **kwargs: Any,
) -> FakeGuild:
    """Create a FakeGuild with defaults."""
    return FakeGuild(
        guild_id=guild_id,
        name=name,
        roles=roles,
        members=members,
        channels=channels,
        **kwargs,
    )


def make_interaction(
    user: FakeMember | FakeUser | None = None,
    guild: FakeGuild | None = None,
    channel: FakeChannel | None = None,
    **kwargs: Any,
) -> FakeInteraction:
    """Create a FakeInteraction with defaults."""
    return FakeInteraction(user=user, guild=guild, channel=channel, **kwargs)


def make_bot(
    guilds: list[FakeGuild] | None = None,
    user: FakeUser | None = None,
) -> FakeBot:
    """Create a FakeBot with defaults."""
    return FakeBot(guilds=guilds, user=user)
