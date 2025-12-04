from unittest.mock import AsyncMock

import pytest

from helpers.views import VerificationView
from tests.test_helpers import FakeInteraction, FakeUser


@pytest.mark.asyncio
async def test_verification_view_buttons_callbacks(monkeypatch, mock_bot) -> None:
    view = VerificationView(mock_bot)

    # Swap callbacks with spies that call original and set flags
    called = {"get_token": False, "verify": False}

    orig_get = view.get_token_button_callback
    orig_verify = view.verify_button_callback

    async def spy_get(ix) -> None:
        called["get_token"] = True
        # Patch internals to avoid network/DB
        monkeypatch.setattr(
            "helpers.views.check_rate_limit", AsyncMock(return_value=(False, 0))
        )
        monkeypatch.setattr("helpers.views.log_attempt", AsyncMock(return_value=None))
        monkeypatch.setattr("helpers.views.send_message", AsyncMock())
        return await orig_get(ix)

    async def spy_verify(ix) -> None:
        called["verify"] = True
        monkeypatch.setattr(
            "helpers.views.check_rate_limit", AsyncMock(return_value=(False, 0))
        )
        return await orig_verify(ix)

    view.get_token_button.callback = spy_get
    view.verify_button.callback = spy_verify

    ix = FakeInteraction(FakeUser(11, "BtnUser"))
    await view.get_token_button.callback(ix)
    await view.verify_button.callback(ix)

    assert called["get_token"] is True
    assert called["verify"] is True
