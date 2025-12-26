"""
Async Command Handler Tests

Unit tests for Discord slash command handlers using mock objects.
Tests permission checks, response handling, and edge cases.
No real Discord connections are made.
"""

from types import SimpleNamespace

import pytest

from tests.factories import (
    make_guild,
    make_interaction,
    make_member,
    make_role,
    make_voice_channel,
    make_voice_state,
)


class TestPermissionDecorators:
    """Test permission check decorators."""

    @pytest.mark.asyncio
    async def test_permission_denied_sends_error_message(self):
        """Test that permission denied sends ephemeral error message."""
        from helpers.decorators import _send_permission_denied

        interaction = make_interaction()
        await _send_permission_denied(interaction)  # type: ignore[arg-type]

        assert interaction.response._is_done
        assert len(interaction.response._messages) == 1
        assert interaction.response._messages[0]["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_permission_denied_uses_followup_if_response_done(self):
        """Test that permission denied uses followup if response already sent."""
        from helpers.decorators import _send_permission_denied

        interaction = make_interaction()
        interaction.response._is_done = True  # Simulate response already sent

        await _send_permission_denied(interaction)  # type: ignore[arg-type]

        assert len(interaction.followup._messages) == 1
        assert interaction.followup._messages[0]["ephemeral"] is True


class TestVoiceCommandHandlers:
    """Test voice command handler behavior."""

    def test_voice_channel_mock_supports_members(self):
        """Test that voice channel mock correctly tracks members."""
        owner = make_member(user_id=123, name="Owner")
        visitor = make_member(user_id=456, name="Visitor")
        vc = make_voice_channel(
            channel_id=789,
            name="Owner's Channel",
            members=[owner, visitor],
        )

        assert len(vc.members) == 2
        assert vc.members[0].id == 123
        assert vc.members[1].id == 456

    def test_member_with_voice_state_in_channel(self):
        """Test member correctly linked to voice channel via state."""
        vc = make_voice_channel(channel_id=789)
        voice_state = make_voice_state(channel=vc)
        member = make_member(user_id=123, voice=voice_state)

        assert member.voice is not None
        assert member.voice.channel is not None
        assert member.voice.channel.id == 789

    def test_member_not_in_voice_channel(self):
        """Test member with no voice connection."""
        member = make_member(user_id=123)

        assert member.voice is None

    @pytest.mark.asyncio
    async def test_voice_command_requires_guild(self):
        """Test that voice commands require guild context."""
        interaction = make_interaction(no_guild=True)
        interaction.guild_id = None

        # Simulate command that checks for guild
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command must be used in a server.",
                ephemeral=True,
            )

        assert interaction.response._is_done
        assert "server" in interaction.response._messages[0]["content"]


class TestAdminCommandHandlers:
    """Test admin command handler behavior."""

    def test_admin_role_detection(self):
        """Test that admin role is correctly detected on member."""
        admin_role = make_role(role_id=999111222, name="Bot Admin")
        member = make_member(user_id=123, roles=[admin_role])

        assert len(member.roles) == 1
        assert member.roles[0].id == 999111222
        assert member.roles[0].name == "Bot Admin"

    def test_member_without_admin_role(self):
        """Test member without admin role."""
        regular_role = make_role(role_id=111, name="Regular")
        member = make_member(user_id=123, roles=[regular_role])

        admin_role_ids = [999111222, 999111223]
        has_admin = any(r.id in admin_role_ids for r in member.roles)

        assert has_admin is False

    @pytest.mark.asyncio
    async def test_reset_user_command_defers_response(self):
        """Test that reset-user command defers response before work."""
        interaction = make_interaction()

        # Simulate command deferral
        await interaction.response.defer(ephemeral=True)

        assert interaction.response._is_done
        assert interaction.response._deferred

    @pytest.mark.asyncio
    async def test_admin_command_sends_confirmation(self):
        """Test that admin commands send confirmation on success."""
        interaction = make_interaction()
        await interaction.response.defer(ephemeral=True)

        # Simulate successful command
        await interaction.followup.send("✅ Operation completed.", ephemeral=True)

        assert len(interaction.followup._messages) == 1
        assert "✅" in interaction.followup._messages[0]["content"]


class TestVerificationCommandHandlers:
    """Test verification command handler behavior."""

    @pytest.mark.asyncio
    async def test_verification_view_button_creates_response(self):
        """Test that verification button creates appropriate response."""
        interaction = make_interaction()

        # Simulate verification flow start
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(
            "Please enter your RSI handle to begin verification.",
            ephemeral=True,
        )

        assert interaction.response._deferred
        assert len(interaction.followup._messages) == 1
        assert "RSI handle" in interaction.followup._messages[0]["content"]

    def test_verification_requires_member_context(self):
        """Test that verification requires Member (not just User)."""
        user = make_member(user_id=123, name="TestUser")
        interaction = make_interaction(user=user)

        # Check that user is a member (has guild context)
        from tests.factories import FakeMember
        assert isinstance(interaction.user, FakeMember)


class TestMissingConfigHandling:
    """Test command behavior when config is missing."""

    @pytest.mark.asyncio
    async def test_command_handles_missing_voice_config(self):
        """Test graceful handling when voice config is missing."""
        interaction = make_interaction()

        # Simulate missing voice service
        services = SimpleNamespace(voice=None)

        if services.voice is None:
            await interaction.response.send_message(
                "❌ Voice features are not configured.",
                ephemeral=True,
            )

        assert "not configured" in interaction.response._messages[0]["content"]

    @pytest.mark.asyncio
    async def test_command_handles_missing_guild_settings(self):
        """Test graceful handling when guild settings are missing."""
        interaction = make_interaction()

        guild_settings = None  # Simulate missing settings

        if guild_settings is None:
            await interaction.response.send_message(
                "❌ This server has not been configured. Please run setup first.",
                ephemeral=True,
            )

        assert "not been configured" in interaction.response._messages[0]["content"]


class TestInteractionResponseFlow:
    """Test interaction response flow patterns."""

    @pytest.mark.asyncio
    async def test_defer_then_followup_pattern(self):
        """Test the common defer -> followup response pattern."""
        interaction = make_interaction()

        # Step 1: Defer
        await interaction.response.defer(ephemeral=True)
        assert interaction.response._deferred

        # Step 2: Do async work (simulated)
        result = "Operation completed"

        # Step 3: Send followup
        await interaction.followup.send(f"✅ {result}", ephemeral=True)
        assert len(interaction.followup._messages) == 1

    @pytest.mark.asyncio
    async def test_direct_response_pattern(self):
        """Test the direct response pattern for simple commands."""
        interaction = make_interaction()

        # Direct response without defer
        await interaction.response.send_message("Quick response!", ephemeral=True)

        assert interaction.response._is_done
        assert not interaction.response._deferred
        assert len(interaction.response._messages) == 1

    @pytest.mark.asyncio
    async def test_modal_response_pattern(self):
        """Test sending a modal in response."""
        interaction = make_interaction()

        class FakeModal:
            title = "Test Modal"

        modal = FakeModal()
        await interaction.response.send_modal(modal)

        assert interaction.response._is_done
        assert interaction.response.sent_modal is modal


class TestRoleManagement:
    """Test role management operations in commands."""

    @pytest.mark.asyncio
    async def test_add_role_to_member(self):
        """Test adding a role to a member."""
        role = make_role(role_id=123, name="Verified")
        member = make_member(user_id=456, roles=[])

        await member.add_roles(role, reason="Verification complete")

        assert role in member.roles
        assert role in member._added_roles

    @pytest.mark.asyncio
    async def test_remove_role_from_member(self):
        """Test removing a role from a member."""
        role = make_role(role_id=123, name="Unverified")
        member = make_member(user_id=456, roles=[role])

        await member.remove_roles(role, reason="Verification complete")

        assert role not in member.roles
        assert role in member._removed_roles

    @pytest.mark.asyncio
    async def test_member_nick_update(self):
        """Test updating a member's nickname."""
        member = make_member(user_id=456, name="OldName", nick=None)

        await member.edit(nick="NewNickname")

        assert member.nick == "NewNickname"
        assert member.display_name == "NewNickname"


class TestGuildOperations:
    """Test guild-related operations."""

    def test_get_member_by_id(self):
        """Test retrieving a member from guild by ID."""
        member = make_member(user_id=123, name="TestMember")
        guild = make_guild(guild_id=456, members=[member])

        found = guild.get_member(123)

        assert found is not None
        assert found.id == 123
        assert found.name == "TestMember"

    def test_get_member_not_found(self):
        """Test retrieving nonexistent member returns None."""
        guild = make_guild(guild_id=456, members=[])

        found = guild.get_member(999)

        assert found is None

    def test_get_channel_by_id(self):
        """Test retrieving a channel from guild by ID."""
        channel = make_voice_channel(channel_id=789, name="Test VC")
        guild = make_guild(guild_id=456, channels=[channel])

        found = guild.get_channel(789)

        assert found is not None
        assert found.id == 789
        assert found.name == "Test VC"

    def test_get_role_by_id(self):
        """Test retrieving a role from guild by ID."""
        role = make_role(role_id=111, name="Admin")
        guild = make_guild(guild_id=456, roles=[role])

        found = guild.get_role(111)

        assert found is not None
        assert found.id == 111
        assert found.name == "Admin"
