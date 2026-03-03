"""Tests for the /privacy info command."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from cogs.info.privacy import PrivacyCog
from tests.test_helpers import FakeInteraction, FakeUser


@pytest.mark.asyncio
async def test_privacy_command_sends_embed_ephemeral(mock_bot) -> None:
    """Command sends privacy embed as an ephemeral response."""
    cog = PrivacyCog(mock_bot)
    interaction = FakeInteraction(FakeUser(1, "Member"))

    interaction.response.send_message = AsyncMock()
    interaction.followup.send = AsyncMock()

    await cog.privacy.callback(cog, interaction)  # type: ignore[arg-type]

    interaction.response.send_message.assert_called_once()
    kwargs = interaction.response.send_message.call_args.kwargs
    assert kwargs["ephemeral"] is True
    assert kwargs["embed"] is not None
    assert kwargs["embed"].title == "TEST Clanker – Privacy & Data Rights"


@pytest.mark.asyncio
async def test_privacy_command_uses_followup_if_response_done(monkeypatch, mock_bot) -> None:
    """Fallback uses followup when initial response has already completed."""
    cog = PrivacyCog(mock_bot)
    interaction = FakeInteraction(FakeUser(1, "Member"))

    interaction.response.send_message = AsyncMock(side_effect=RuntimeError("boom"))
    interaction.response.is_done = MagicMock(return_value=True)
    interaction.followup.send = AsyncMock()

    monkeypatch.setattr(
        "cogs.info.privacy.build_privacy_embed",
        MagicMock(side_effect=RuntimeError("embed-fail")),
    )
    monkeypatch.setattr("cogs.info.privacy.logger.exception", MagicMock())

    await cog.privacy.callback(cog, interaction)  # type: ignore[arg-type]

    interaction.followup.send.assert_called_once_with(
        "❌ Unable to show privacy info right now. Please try again later.",
        ephemeral=True,
    )
