"""Tests for the Help command cog."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from cogs.info.help import (
    ALL_COMMANDS,
    HelpCog,
    build_help_embeds,
    get_accessible_commands,
)
from helpers.permissions_helper import PermissionLevel
from tests.test_helpers import FakeInteraction, FakeUser


def _make_member_interaction() -> FakeInteraction:
    """Create a FakeInteraction with a user that passes isinstance(discord.Member)."""
    member = MagicMock(spec=discord.Member)
    member.id = 1
    member.display_name = "TestUser"
    interaction = FakeInteraction(member)
    interaction.guild = SimpleNamespace(id=123, name="TestGuild")
    return interaction


class TestGetAccessibleCommands:
    """Tests for command filtering by permission level."""

    def test_user_level_sees_only_public_commands(self) -> None:
        """Regular users should only see commands available to USER level."""
        user_level = PermissionLevel.USER
        accessible = get_accessible_commands(user_level)

        assert "Info" in accessible
        assert "Voice" in accessible
        total_commands = sum(len(cmds) for cmds in accessible.values())
        assert total_commands > 0
        # Verify no admin commands are included
        for category_cmds in accessible.values():
            for cmd in category_cmds:
                assert cmd.permission_level == PermissionLevel.USER

    def test_staff_level_includes_staff_commands(self) -> None:
        """Staff level should include staff and lower commands."""
        staff_level = PermissionLevel.STAFF
        accessible = get_accessible_commands(staff_level)

        assert "Info" in accessible
        # Verify we can see dashboard command which is staff+
        dashboard_cmds = [cmd for cmd in accessible["Info"] if "/dashboard" in cmd.name]
        assert len(dashboard_cmds) > 0
        # Verify no bot admin commands are included
        for category_cmds in accessible.values():
            for cmd in category_cmds:
                assert cmd.permission_level <= PermissionLevel.STAFF

    def test_moderator_level_includes_verification_commands(self) -> None:
        """Moderator level should include all verification and voice admin commands."""
        mod_level = PermissionLevel.MODERATOR
        accessible = get_accessible_commands(mod_level)

        assert "Verification" in accessible
        assert "Voice" in accessible
        # Verify we can see reset-user command
        all_cmds = [
            cmd for category_cmds in accessible.values() for cmd in category_cmds
        ]
        reset_user_cmds = [cmd for cmd in all_cmds if "/reset-user" in cmd.name]
        assert len(reset_user_cmds) > 0
        # Verify moderator can't see /reset-all (bot admin only)
        reset_all_cmds = [cmd for cmd in all_cmds if "/reset-all" in cmd.name]
        assert len(reset_all_cmds) == 0

    def test_bot_admin_level_sees_all_commands(self) -> None:
        """Bot admin should see all commands."""
        admin_level = PermissionLevel.BOT_ADMIN
        accessible = get_accessible_commands(admin_level)

        all_cmds = [
            cmd for category_cmds in accessible.values() for cmd in category_cmds
        ]
        # Should include /reset-all (admin only)
        reset_all_cmds = [cmd for cmd in all_cmds if "/reset-all" in cmd.name]
        assert len(reset_all_cmds) > 0
        # Most importantly: should have commands from all categories
        assert len(accessible) >= 5  # At least these

    def test_permission_level_hierarchy(self) -> None:
        """Verify permission level hierarchy is correct."""
        user_cmds = get_accessible_commands(PermissionLevel.USER)
        staff_cmds = get_accessible_commands(PermissionLevel.STAFF)
        mod_cmds = get_accessible_commands(PermissionLevel.MODERATOR)
        admin_cmds = get_accessible_commands(PermissionLevel.BOT_ADMIN)

        # Count total commands visible at each level
        user_total = sum(len(cmds) for cmds in user_cmds.values())
        staff_total = sum(len(cmds) for cmds in staff_cmds.values())
        mod_total = sum(len(cmds) for cmds in mod_cmds.values())
        admin_total = sum(len(cmds) for cmds in admin_cmds.values())

        # Assert: each level should see increasingly more commands
        assert user_total <= staff_total
        assert staff_total <= mod_total
        assert mod_total <= admin_total


class TestBuildHelpEmbeds:
    """Tests for embed generation."""

    def test_builds_embeds_without_errors(self) -> None:
        """Embeds should be generated without truncation or errors."""
        commands = get_accessible_commands(PermissionLevel.BOT_ADMIN)
        level = PermissionLevel.BOT_ADMIN

        embeds = build_help_embeds(commands, level)

        assert len(embeds) > 0
        # First embed should be summary
        summary = embeds[0]
        assert summary.title == "📋 TEST Clanker Command Help"
        assert summary.color is not None and summary.color.value == 0x3498DB
        # Should have at least summary + one category embed
        assert len(embeds) >= 2

    def test_embeds_contain_all_commands(self) -> None:
        """All filtered commands should appear in the embeds."""
        commands = get_accessible_commands(PermissionLevel.MODERATOR)
        level = PermissionLevel.MODERATOR

        embeds = build_help_embeds(commands, level)

        # Assert: collect all command names from embeds (skip summary)
        embed_text = ""
        for embed in embeds[1:]:  # Skip summary embed
            for field in embed.fields:
                embed_text += (field.name or "") + " "

        # Verify key commands appear
        assert "/check user" in embed_text or "check" in embed_text
        assert "/reset-user" in embed_text or "reset-user" in embed_text

    def test_embeds_have_proper_footer(self) -> None:
        """Embeds should have proper footer with permission level."""
        commands = get_accessible_commands(PermissionLevel.STAFF)
        level = PermissionLevel.STAFF

        embeds = build_help_embeds(commands, level)

        # Assert: category embeds should have permission level in footer
        category_embeds = embeds[1:]
        assert len(category_embeds) > 0
        for embed in category_embeds:
            assert embed.footer.text is not None
            assert "STAFF" in embed.footer.text

    def test_embed_colors_are_consistent(self) -> None:
        """All embeds should use the same blue color."""
        commands = get_accessible_commands(PermissionLevel.USER)
        level = PermissionLevel.USER

        embeds = build_help_embeds(commands, level)

        # Assert: all embeds should be blue
        for embed in embeds:
            assert embed.color is not None and embed.color.value == 0x3498DB

    def test_summary_embed_counts_commands_correctly(self) -> None:
        """Summary embed should correctly count the number of commands."""
        commands = get_accessible_commands(PermissionLevel.MODERATOR)
        level = PermissionLevel.MODERATOR
        expected_count = sum(len(cmds) for cmds in commands.values())

        embeds = build_help_embeds(commands, level)

        # Assert: summary embed should mention the count
        summary = embeds[0]
        assert summary.description is not None
        assert str(expected_count) in summary.description


@pytest.mark.asyncio
async def test_help_command_defers_and_responds(mock_bot) -> None:
    """Help command should defer and send embeds."""
    cog = HelpCog(mock_bot)
    interaction = _make_member_interaction()

    # Track calls
    defer_called = False
    followup_send_called = False
    embeds_sent = []

    async def fake_defer(**kwargs: object) -> None:
        nonlocal defer_called
        defer_called = True

    async def fake_followup_send(
        embeds: object = None, ephemeral: bool = False, **kwargs: object
    ) -> None:
        nonlocal followup_send_called, embeds_sent
        followup_send_called = True
        if embeds:
            embeds_sent = embeds

    interaction.response.defer = fake_defer  # type: ignore[assignment]
    interaction.followup.send = fake_followup_send  # type: ignore[assignment]

    # Mock get_permission_level to return MODERATOR
    with patch(
        "cogs.info.help.get_permission_level",
        new_callable=AsyncMock,
        return_value=PermissionLevel.MODERATOR,
    ):
        # Act
        await cog.help_command.callback(cog, interaction)  # type: ignore[arg-type]

    # Assert
    assert defer_called
    assert followup_send_called
    assert len(embeds_sent) > 0


@pytest.mark.asyncio
async def test_help_command_shows_moderator_commands() -> None:
    """Help command should show appropriate commands for moderator."""
    cog = HelpCog(MagicMock())
    interaction = _make_member_interaction()

    embeds_sent: list[discord.Embed] = []

    async def fake_defer(**kwargs: object) -> None:
        pass

    async def fake_followup_send(
        embeds: list[discord.Embed] | None = None,
        ephemeral: bool = False,
        **kwargs: object,
    ) -> None:
        if embeds:
            embeds_sent.extend(embeds)

    interaction.response.defer = fake_defer  # type: ignore[assignment]
    interaction.followup.send = fake_followup_send  # type: ignore[assignment]

    # Mock get_permission_level to return MODERATOR
    with patch(
        "cogs.info.help.get_permission_level",
        new_callable=AsyncMock,
        return_value=PermissionLevel.MODERATOR,
    ):
        # Act
        await cog.help_command.callback(cog, interaction)  # type: ignore[arg-type]

    # Assert: embeds should contain moderator-level commands
    embed_text = "".join(
        (field.name or "") + " " + (field.value or "")
        for embed in embeds_sent
        for field in embed.fields
    )
    # Should have verification commands
    assert any(cmd in embed_text for cmd in ["/check user", "/reset-user", "/verify"])


@pytest.mark.asyncio
async def test_help_command_requires_guild() -> None:
    """Help command should fail gracefully outside of guild."""
    cog = HelpCog(MagicMock())
    user = FakeUser()
    interaction = FakeInteraction(user)
    interaction.guild = None  # type: ignore[assignment]  # No guild

    response_sent: list[str] = []

    async def fake_send_message(
        message: str, ephemeral: bool = False, **kwargs: object
    ) -> None:
        response_sent.append(message)

    interaction.response.send_message = fake_send_message  # type: ignore[assignment]

    # Act
    await cog.help_command.callback(cog, interaction)  # type: ignore[arg-type]

    # Assert: should send error message
    assert len(response_sent) > 0
    assert "server" in response_sent[0].lower()


@pytest.mark.asyncio
async def test_help_command_handles_exceptions() -> None:
    """Help command should handle exceptions gracefully."""
    cog = HelpCog(MagicMock())
    interaction = _make_member_interaction()

    followup_called = False

    async def fake_defer(**kwargs: object) -> None:
        interaction.response._is_done = True

    async def fake_followup_send(
        *args: object, ephemeral: bool = False, **kwargs: object
    ) -> None:
        nonlocal followup_called
        followup_called = True

    interaction.response.defer = fake_defer  # type: ignore[assignment]
    interaction.followup.send = fake_followup_send  # type: ignore[assignment]

    # Mock get_permission_level to raise exception
    with patch(
        "cogs.info.help.get_permission_level",
        new_callable=AsyncMock,
        side_effect=Exception("Test error"),
    ):
        # Act
        await cog.help_command.callback(cog, interaction)  # type: ignore[arg-type]

    # Assert: should have sent error message
    assert followup_called


def test_all_commands_have_metadata() -> None:
    """Every command should have proper metadata."""
    for cmd in ALL_COMMANDS:
        assert cmd.name, "Command should have a name"
        assert "/" in cmd.name, "Command name should start with /"
        assert cmd.description, "Command should have a description"
        assert len(cmd.description) > 0, "Description should not be empty"
        assert cmd.category, "Command should have a category"
        assert isinstance(cmd.permission_level, PermissionLevel), (
            "Should have valid permission level"
        )


def test_command_count_and_coverage() -> None:
    """Verify all 26 commands are present."""
    total = len(ALL_COMMANDS)

    # Assert: Should have all commands
    assert total >= 26, f"Should have at least 26 commands, got {total}"

    # Verify we have commands from each permission level
    user_cmds = [c for c in ALL_COMMANDS if c.permission_level == PermissionLevel.USER]
    staff_cmds = [
        c for c in ALL_COMMANDS if c.permission_level == PermissionLevel.STAFF
    ]
    mod_cmds = [
        c for c in ALL_COMMANDS if c.permission_level == PermissionLevel.MODERATOR
    ]
    admin_cmds = [
        c for c in ALL_COMMANDS if c.permission_level == PermissionLevel.BOT_ADMIN
    ]

    assert len(user_cmds) > 0, "Should have USER level commands"
    assert len(staff_cmds) > 0, "Should have STAFF level commands"
    assert len(mod_cmds) > 0, "Should have MODERATOR level commands"
    assert len(admin_cmds) > 0, "Should have BOT_ADMIN level commands"
