from unittest.mock import AsyncMock

import pytest
from helpers.views import VerificationView
from tests.conftest import FakeInteraction, FakeUser


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

    # Patch send_message to capture calls
    sent = {"called": False}

    async def fake_send_message(
        interaction, content, ephemeral=False, embed=None, view=None
    ) -> None:
        sent["called"] = True
        assert ephemeral is True
        assert embed is not None

    monkeypatch.setattr("helpers.views.send_message", fake_send_message)

    ix = FakeInteraction(FakeUser(7, "TestUser"))
    await view.get_token_button_callback(ix)
    assert sent["called"] is True


@pytest.mark.asyncio
async def test_verify_button_opens_modal_when_not_rate_limited(
    monkeypatch, mock_bot
) -> None:
    view = VerificationView(mock_bot)
    monkeypatch.setattr(
        "helpers.views.check_rate_limit", AsyncMock(return_value=(False, 0))
    )

    ix = FakeInteraction(FakeUser(8, "VerifUser"))
    await view.verify_button_callback(ix)
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
    await view.recheck_button_callback(ix)
    assert fake_cog.called is True
