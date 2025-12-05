from unittest.mock import AsyncMock

import pytest

from helpers.views import FeatureRoleSelectView, FeatureUserSelectView, SelectUserView
from tests.test_helpers import FakeInteraction, FakeUser


# Simple mock classes to replace dynamic type() calls
class FakeSelect:
    def __init__(self, values):
        self.values = values


class FakeRole:
    def __init__(self, rid):
        self.id = int(rid)
        self.name = "Role"
        self.mention = f"<@&{rid}>"


class FakeGuildForUI:
    def __init__(self, guild_id, default_role=None):
        self.id = guild_id
        self.name = "Guild"
        self.default_role = default_role

    def get_role(self, rid):
        return FakeRole(rid)


class FakeChannelUI:
    def __init__(self, channel_id, guild_obj):
        self.id = channel_id
        self.name = "TestChannel"
        self.guild = guild_obj


@pytest.mark.asyncio
async def test_feature_user_select_calls_db_and_apply(monkeypatch, mock_bot) -> None:
    view = FeatureUserSelectView(mock_bot, feature_name="ptt", enable=True)

    # Prepare fake selected users
    target = FakeUser(2000, "TargetUser")
    # Replace select with a mock object that has writable values
    view.user_select = FakeSelect([target])  # type: ignore[assignment]

    # Create fake guild and channel
    fake_guild = FakeGuildForUI(999, default_role=None)
    fake_channel = FakeChannelUI(42, fake_guild)

    monkeypatch.setattr(
        "helpers.views.get_user_channel", AsyncMock(return_value=fake_channel)
    )
    # Patch the helper that resolves guild/jtc
    monkeypatch.setattr(
        "helpers.views._get_guild_and_jtc_for_user_channel",
        AsyncMock(return_value=(999, 555)),
    )

    fake_set = AsyncMock()
    fake_apply = AsyncMock()
    fake_send = AsyncMock()
    monkeypatch.setattr("helpers.views.set_voice_feature_setting", fake_set)
    monkeypatch.setattr("helpers.views.apply_voice_feature_toggle", fake_apply)
    monkeypatch.setattr("helpers.views.send_message", fake_send)

    ix = FakeInteraction(FakeUser(1000, "Owner"))
    await view.user_select_callback(ix)  # type: ignore[arg-type]

    # assert DB set called for the selected user
    assert fake_set.await_count == 1
    # assert apply called to modify channel overwrites
    assert fake_apply.await_count == 1
    # assert a message was sent back to user
    assert fake_send.await_count >= 1


@pytest.mark.asyncio
async def test_select_user_store_permit_calls_db_and_apply(
    monkeypatch, mock_bot
) -> None:
    view = SelectUserView(mock_bot, action="permit")

    # selected target user objects
    t1 = FakeUser(3000, "TargetA")
    view.user_select = FakeSelect([t1])  # type: ignore[assignment]

    fake_guild = FakeGuildForUI(111)
    fake_channel = FakeChannelUI(99, fake_guild)

    monkeypatch.setattr(
        "helpers.views.get_user_channel", AsyncMock(return_value=fake_channel)
    )
    monkeypatch.setattr(
        "helpers.views._get_guild_and_jtc_for_user_channel",
        AsyncMock(return_value=(111, 222)),
    )

    fake_store = AsyncMock()
    fake_apply = AsyncMock()
    fake_send = AsyncMock()
    monkeypatch.setattr("helpers.views.store_permit_reject_in_db", fake_store)
    monkeypatch.setattr("helpers.views.apply_permissions_changes", fake_apply)
    monkeypatch.setattr("helpers.views.send_message", fake_send)

    ix = FakeInteraction(FakeUser(5000, "OwnerTwo"))
    await view.user_select_callback(ix)  # type: ignore[arg-type]

    assert fake_store.await_count == 1
    assert fake_apply.await_count == 1
    assert fake_send.await_count == 1


@pytest.mark.asyncio
async def test_feature_role_select_calls_db_and_apply(monkeypatch, mock_bot) -> None:
    view = FeatureRoleSelectView(mock_bot, feature_name="soundboard", enable=True)

    # role select stores strings of ids; replace with a fake select object
    view.role_select = FakeSelect(["4444"])  # type: ignore[assignment]

    fake_guild = FakeGuildForUI(777)
    fake_channel = FakeChannelUI(201, fake_guild)

    monkeypatch.setattr(
        "helpers.views.get_user_channel", AsyncMock(return_value=fake_channel)
    )
    monkeypatch.setattr(
        "helpers.views._get_guild_and_jtc_for_user_channel",
        AsyncMock(return_value=(777, 888)),
    )

    fake_set = AsyncMock()
    fake_apply = AsyncMock()
    fake_send = AsyncMock()
    monkeypatch.setattr("helpers.views.set_voice_feature_setting", fake_set)
    monkeypatch.setattr("helpers.views.apply_voice_feature_toggle", fake_apply)
    monkeypatch.setattr("helpers.views.send_message", fake_send)

    ix = FakeInteraction(FakeUser(6000, "OwnerThree"))
    # Ensure interaction.guild is our fake guild object
    ix.guild = fake_guild  # type: ignore[assignment]

    await view.role_select_callback(ix)  # type: ignore[arg-type]

    assert fake_set.await_count == 1
    assert fake_apply.await_count == 1
    assert fake_send.await_count == 1
