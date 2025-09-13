from unittest.mock import AsyncMock

import pytest
from helpers.views import FeatureRoleSelectView, FeatureUserSelectView, SelectUserView
from tests.conftest import FakeInteraction, FakeUser


@pytest.mark.asyncio
async def test_feature_user_select_calls_db_and_apply(monkeypatch, mock_bot) -> None:
    view = FeatureUserSelectView(mock_bot, feature_name="ptt", enable=True)

    # Prepare fake selected users
    target = FakeUser(2000, "TargetUser")
    # discord.ui.Select.values is a read-only property; replace the select
    # with a simple fake object that exposes a writable `values` attribute.
    view.user_select = type("S", (), {"values": [target]})()

    # Monkeypatch get_user_channel to return a fake channel
    fake_channel = type("C", (), {})()
    fake_channel.guild = type("G", (), {"id": 999, "name": "G", "default_role": None})()
    fake_channel.id = 42
    fake_channel.name = "OwnerChannel"

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
    await view.user_select_callback(ix)

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
    view.user_select = type("S", (), {"values": [t1]})()

    fake_channel = type("C", (), {})()
    fake_channel.guild = type("G", (), {"id": 111, "name": "Guild"})()
    fake_channel.id = 99

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
    await view.user_select_callback(ix)

    assert fake_store.await_count == 1
    assert fake_apply.await_count == 1
    assert fake_send.await_count == 1


@pytest.mark.asyncio
async def test_feature_role_select_calls_db_and_apply(monkeypatch, mock_bot) -> None:
    view = FeatureRoleSelectView(mock_bot, feature_name="soundboard", enable=True)

    # role select stores strings of ids; replace with a fake select object
    view.role_select = type("S", (), {"values": ["4444"]})()

    fake_channel = type("C", (), {})()
    fake_guild = type("G", (), {})()

    # guild.get_role should return a role-like object
    def get_role(rid) -> None:
        return type(
            "R", (), {"id": int(rid), "name": "Role", "mention": f"<@&{rid}>"}
        )()

    fake_guild.get_role = get_role
    fake_guild.id = 777
    fake_channel.guild = fake_guild
    fake_channel.id = 201
    fake_channel.name = "Ch"

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
    ix.guild = fake_guild

    await view.role_select_callback(ix)

    assert fake_set.await_count == 1
    assert fake_apply.await_count == 1
    assert fake_send.await_count == 1
