import pytest

from cogs.admin.commands import AdminCog
from tests.test_helpers import FakeInteraction, FakeUser


@pytest.mark.asyncio
async def test_admin_status_returns_expected_string(monkeypatch, mock_bot) -> None:
    # Mock the health service to return a simple status
    mock_health = type("MockHealth", (), {})()

    async def mock_run_health_checks(bot, services):
        return {
            "overall_status": "healthy",
            "services": {},
            "database": {"status": "healthy"},
            "uptime": "1h",
        }

    mock_health.run_health_checks = mock_run_health_checks

    # Mock service container to return our mock health service
    mock_services = type("MockServices", (), {})()
    mock_services.health = mock_health
    mock_services.get_all_services = lambda: []
    mock_bot.services = mock_services

    # Mock admin permission check
    async def mock_has_admin_permissions(user, guild=None):
        return True

    mock_bot.has_admin_permissions = mock_has_admin_permissions

    # Capture response - need to handle both send_message and followup
    captured = {}

    async def capture_response(content=None, embed=None, ephemeral=False, **kwargs):
        captured["content"] = str(embed.description) if embed else content
        captured["ephemeral"] = ephemeral
        captured["embed"] = embed

    # Build cog and run
    cog = AdminCog(mock_bot)
    ix = FakeInteraction(FakeUser(10, "AdminUser"))
    ix.response.send_message = capture_response
    ix.followup.send = capture_response

    # Call the status command directly
    await cog.status.callback(cog, ix)

    # Check that some status content was returned (could be in embed or content)
    assert captured.get("embed") is not None or captured.get("content") is not None
