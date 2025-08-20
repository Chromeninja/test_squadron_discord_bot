import pytest
from unittest.mock import AsyncMock

from cogs import admin as admin_cog
from tests.conftest import FakeInteraction, FakeUser


@pytest.mark.asyncio
async def test_admin_status_returns_expected_string(monkeypatch, mock_bot):
    # Patch send_message to capture payload
    captured = {}

    async def fake_send_message(interaction, content, ephemeral=False, embed=None, view=None):
        captured["content"] = content
        captured["ephemeral"] = ephemeral
        return None

    monkeypatch.setattr("cogs.admin.send_message", fake_send_message)

    # Build cog and run
    cog = admin_cog.Admin(mock_bot)
    ix = FakeInteraction(FakeUser(10, "AdminUser"))

    # Patch permission checks to bypass app_commands role checks by directly calling method
    # app_commands turns methods into Command objects; call the underlying callback
    await cog.status.callback(cog, ix)

    assert "online and operational" in captured.get("content", "").lower()
    assert captured.get("ephemeral") is True
