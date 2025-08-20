import pytest

from helpers.views import ChannelSettingsView


import pytest


@pytest.mark.asyncio
async def test_channel_settings_select_has_custom_id_and_persistent_timeout(mock_bot):
    view = ChannelSettingsView(mock_bot)

    # View should be persistent
    assert view.timeout is None

    # The first dropdown (Channel Settings) should have a stable custom_id
    select = view.channel_settings_select
    assert isinstance(select.custom_id, str)
    assert 1 <= len(select.custom_id) <= 100
    assert select.custom_id == "channel_settings_select_main"
