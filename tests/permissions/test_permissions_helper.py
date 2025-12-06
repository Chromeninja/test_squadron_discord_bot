from typing import TYPE_CHECKING, cast

import pytest

from helpers import permissions_helper as ph

if TYPE_CHECKING:
    import discord


class DummyGuildPermissions:
    administrator = False


class DummyGuild:
    def __init__(self, guild_id: int = 1):
        self.id = guild_id
        self.owner_id = None


class DummyRole:
    def __init__(self, role_id: int):
        self.id = role_id


class DummyMember:
    def __init__(self, role_ids, guild: DummyGuild | None = None):
        self.id = 123
        self.roles = [DummyRole(rid) for rid in role_ids]
        self.guild = guild or DummyGuild()
        self.guild_permissions = DummyGuildPermissions()


class DummyConfig:
    def __init__(self, role_map: dict[str, list]):
        self.role_map = role_map

    async def get_guild_setting(self, guild_id: int, key: str, default):
        return self.role_map.get(key, default)


class DummyServices:
    def __init__(self, config):
        self.config = config


class DummyBot:
    def __init__(self, role_map: dict[str, list]):
        self.owner_id = None
        self.services = DummyServices(DummyConfig(role_map))


@pytest.fixture(autouse=True)
def patch_discord_types(monkeypatch):
    monkeypatch.setattr(ph.discord, "Member", DummyMember)
    monkeypatch.setattr(ph.discord, "Guild", DummyGuild)
    yield


@pytest.mark.asyncio
async def test_permission_level_handles_invalid_roles():
    role_map = {
        "roles.bot_admins": ["not-a-number", None],
        "roles.discord_managers": ["abc"],
        "roles.moderators": ["nan"],
        "roles.staff": ["zzz"],
    }
    bot = DummyBot(role_map)
    member = DummyMember(role_ids=[999], guild=DummyGuild())

    level = await ph.get_permission_level(
        bot,
        cast("discord.Member", member),
        cast("discord.Guild", member.guild),
    )

    assert level == ph.PermissionLevel.USER


@pytest.mark.asyncio
async def test_permission_level_uses_db_roles_only():
    role_map = {
        "roles.bot_admins": [],
        "roles.discord_managers": ["42", "42"],
        "roles.moderators": [],
        "roles.staff": [],
    }
    bot = DummyBot(role_map)
    guild = DummyGuild()
    member = DummyMember(role_ids=[42], guild=guild)

    level = await ph.get_permission_level(
        bot,
        cast("discord.Member", member),
        cast("discord.Guild", guild),
    )

    assert level == ph.PermissionLevel.DISCORD_MANAGER
