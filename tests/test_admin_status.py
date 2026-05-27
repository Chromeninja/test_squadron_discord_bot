from types import SimpleNamespace
from typing import Any

import pytest

from cogs.admin.commands import AdminCog
from tests.test_helpers import FakeInteraction, FakeUser


@pytest.mark.asyncio
async def test_admin_status_returns_expected_string(
    monkeypatch: pytest.MonkeyPatch,
    mock_bot: Any,
) -> None:
    # Mock the health service to return a simple status
    mock_health = SimpleNamespace()

    async def mock_run_health_checks(bot: Any, services: Any) -> dict[str, Any]:
        return {
            "overall_status": "healthy",
            "services": {},
            "database": {"status": "healthy"},
            "uptime": "1h",
        }

    mock_health.run_health_checks = mock_run_health_checks

    # Mock service container to return our mock health service
    mock_services = SimpleNamespace()
    mock_services.health = mock_health
    mock_services.get_all_services = lambda: []
    mock_bot.services = mock_services

    # Mock admin permission check
    async def mock_has_admin_permissions(
        user: Any,
        guild: Any = None,
    ) -> bool:
        return True

    mock_bot.has_admin_permissions = mock_has_admin_permissions

    # Capture response - need to handle both send_message and followup
    captured_content: str | None = None
    captured_ephemeral = False
    captured_embed: Any | None = None

    async def capture_response(
        content: str | None = None,
        embed: Any | None = None,
        ephemeral: bool = False,
        **kwargs: Any,
    ) -> None:
        nonlocal captured_content, captured_ephemeral, captured_embed
        captured_content = str(embed.description) if embed is not None else content
        captured_ephemeral = ephemeral
        captured_embed = embed

    # Build cog and run
    cog = AdminCog(mock_bot)
    ix = FakeInteraction(FakeUser(10, "AdminUser"))
    response: Any = ix.response
    followup: Any = ix.followup
    response.send_message = capture_response
    followup.send = capture_response

    # Call the status command directly
    await cog.status.callback(cog, ix)  # type: ignore[arg-type]

    # Check that some status content was returned (could be in embed or content)
    assert captured_embed is not None or captured_content is not None
