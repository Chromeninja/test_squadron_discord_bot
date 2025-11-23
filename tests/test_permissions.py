from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import helpers.permissions_helper as perms


class DummyRole(SimpleNamespace):
    """Minimal role-like object exposing an id attribute."""


def _make_role(role_id: int) -> DummyRole:
    return DummyRole(id=role_id)


class DummyGuild(SimpleNamespace):
    def __init__(self, guild_id: int, owner_id: int):
        super().__init__(id=guild_id, owner_id=owner_id)


class DummyPermissions(SimpleNamespace):
    def __init__(self, administrator: bool = False):
        super().__init__(administrator=administrator)


class DummyMember:
    def __init__(
        self,
        guild: DummyGuild,
        role_ids: list[int] | None = None,
        *,
        member_id: int = 0,
        admin: bool = False,
    ) -> None:
        self.guild = guild
        self.roles = [_make_role(role_id) for role_id in (role_ids or [])]
        self.guild_permissions = DummyPermissions(administrator=admin)
        self.id = member_id


@pytest.fixture(autouse=True)
def patch_discord_member(monkeypatch):
    monkeypatch.setattr(perms.discord, "Member", DummyMember)
    yield
    monkeypatch.setattr(perms.discord, "Member", DummyMember)


@pytest.fixture
def config_service():
    service = SimpleNamespace()
    service.get_guild_setting = AsyncMock()
    return service


@pytest.fixture
def mock_bot(config_service):
    bot = SimpleNamespace()
    bot.owner_id = 77
    bot.services = SimpleNamespace(config=config_service)
    return bot


@pytest.mark.asyncio
async def test_bot_admin_role_allows_access(mock_bot, config_service):
    guild = DummyGuild(123, owner_id=456)
    member = DummyMember(guild, role_ids=[999], member_id=200)

    config_service.get_guild_setting.side_effect = [[999], []]

    result = await perms.is_bot_admin_only(mock_bot, member)

    assert result is True
    config_service.get_guild_setting.assert_any_await(123, "roles.bot_admins", [])


@pytest.mark.asyncio
async def test_lead_mod_role_allows_access(mock_bot, config_service):
    guild = DummyGuild(123, owner_id=456)
    member = DummyMember(guild, role_ids=[555], member_id=200)

    config_service.get_guild_setting.side_effect = [[], [555]]

    result = await perms.is_lead_moderator_or_higher(mock_bot, member)

    assert result is True


@pytest.mark.asyncio
async def test_guild_owner_fallback(mock_bot, config_service):
    guild = DummyGuild(123, owner_id=200)
    member = DummyMember(guild, role_ids=[], member_id=200)

    result = await perms.is_lead_moderator_or_higher(mock_bot, member)

    assert result is True


@pytest.mark.asyncio
async def test_permission_denied_without_roles(mock_bot, config_service):
    guild = DummyGuild(123, owner_id=456)
    member = DummyMember(guild, role_ids=[1], member_id=300)

    config_service.get_guild_setting.side_effect = [[], []]

    result = await perms.is_bot_admin_only(mock_bot, member)

    assert result is False
