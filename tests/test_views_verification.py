from unittest.mock import AsyncMock

import pytest

from helpers.views import VerificationView
from tests.test_helpers import FakeInteraction, FakeUser


@pytest.mark.asyncio
async def test_get_token_button_calls_rate_limit_and_sends_embed(
    monkeypatch, mock_bot
) -> None:
    view = VerificationView(mock_bot)

    # Patch rate limiter and attempt logging (avoid DB)
    monkeypatch.setattr(
        "helpers.views.check_rate_limit", AsyncMock(return_value=(False, 0))
    )
    monkeypatch.setattr("helpers.views.log_attempt", AsyncMock(return_value=None))

    # Track interaction calls
    ix = FakeInteraction(FakeUser(7, "TestUser"))
    defer_called = False
    followup_called = False

    async def fake_defer(ephemeral=False):
        nonlocal defer_called
        defer_called = True
        assert ephemeral is True

    async def fake_followup_send(content, ephemeral=False, embed=None, **kwargs):
        nonlocal followup_called
        followup_called = True
        assert ephemeral is True
        assert embed is not None

    ix.response.defer = fake_defer
    ix.followup.send = fake_followup_send

    await view.get_token_button_callback(ix)  # type: ignore[arg-type]
    assert defer_called is True
    assert followup_called is True


@pytest.mark.asyncio
async def test_verify_button_opens_modal_when_not_rate_limited(
    monkeypatch, mock_bot
) -> None:
    view = VerificationView(mock_bot)
    # No longer need to patch check_rate_limit - it's been removed from button callback

    ix = FakeInteraction(FakeUser(8, "VerifUser"))
    await view.verify_button_callback(ix)  # type: ignore[arg-type]
    # The FakeResponse stores the modal
    assert ix.response.sent_modal is not None


@pytest.mark.asyncio
async def test_recheck_button_forwards_to_cog(monkeypatch, mock_bot) -> None:
    view = VerificationView(mock_bot)

    # Attach a fake VerificationCog with method recheck_button
    class FakeCog:
        def __init__(self) -> None:
            self.called = False

        async def recheck_button(self, interaction) -> None:
            self.called = True

    fake_cog = FakeCog()
    mock_bot._cog_VerificationCog = fake_cog

    ix = FakeInteraction(FakeUser(9, "Recheck"))
    await view.recheck_button_callback(ix)  # type: ignore[arg-type]
    assert fake_cog.called is True
