import pytest

from helpers import role_select_utils as rsu


class DummyGuild:
    def __init__(self, guild_id: int = 1):
        self.id = guild_id


class DummySelect:
    def __init__(self):
        self.allowed_roles = []
        self.refreshed_for = None

    def refresh_options(self, guild):
        self.refreshed_for = guild


def build_bot(role_config: dict[str, list]):
    class _Config:
        async def get_guild_setting(self, guild_id: int, key: str, default):
            return role_config.get(key, default)

    class _Services:
        def __init__(self):
            self.config = _Config()

    class _Bot:
        def __init__(self):
            self.services = _Services()

    return _Bot()


@pytest.mark.asyncio
async def test_load_selectable_roles_normalizes_and_dedupes():
    bot = build_bot({"selectable_roles": ["1", ["1", "5"], -1, "99", "abc"]})
    guild = DummyGuild()

    roles = await rsu.load_selectable_roles(bot, guild)

    assert roles == [1, 5, 99]


@pytest.mark.asyncio
async def test_load_selectable_roles_falls_back_to_legacy_key():
    bot = build_bot({"roles.selectable": ["2", "4", "2"]})
    guild = DummyGuild()

    roles = await rsu.load_selectable_roles(bot, guild)

    assert roles == [2, 4]


@pytest.mark.asyncio
async def test_load_selectable_roles_missing_services_returns_empty():
    class _Bot:
        services = None

    bot = _Bot()
    roles = await rsu.load_selectable_roles(bot, DummyGuild())

    assert roles == []


def test_refresh_role_select_updates_widget_and_refreshes():
    select = DummySelect()
    guild = DummyGuild()

    rsu.refresh_role_select(select, guild, [5, 6])

    assert select.allowed_roles == [5, 6]
    assert select.refreshed_for is guild
