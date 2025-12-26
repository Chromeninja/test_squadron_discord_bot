"""
Test Factories Module

Centralized factory functions and fixtures for creating test objects.
Provides DRY utilities for Discord mocks, sample HTML, config fixtures, and DB seeding.
"""

from .config_factories import (
    make_config,
    make_minimal_config,
    temp_config_file,
)
from .db_factories import (
    seed_guild_settings,
    seed_jtc_preferences,
    seed_verification_records,
    seed_voice_channels,
)
from .discord_factories import (
    FakeBot,
    FakeChannel,
    FakeGuild,
    FakeInteraction,
    FakeMember,
    FakeRole,
    FakeUser,
    FakeVoiceChannel,
    FakeVoiceState,
    make_bot,
    make_channel,
    make_guild,
    make_interaction,
    make_member,
    make_role,
    make_user,
    make_voice_channel,
    make_voice_state,
)
from .html_factories import (
    load_sample_html,
    make_bio_html,
    make_org_html,
)

__all__ = [
    "FakeBot",
    "FakeChannel",
    "FakeGuild",
    "FakeInteraction",
    "FakeMember",
    "FakeRole",
    "FakeUser",
    "FakeVoiceChannel",
    "FakeVoiceState",
    "load_sample_html",
    "make_bio_html",
    "make_bot",
    "make_channel",
    "make_config",
    "make_guild",
    "make_interaction",
    "make_member",
    "make_minimal_config",
    "make_org_html",
    "make_role",
    "make_user",
    "make_voice_channel",
    "make_voice_state",
    "seed_guild_settings",
    "seed_jtc_preferences",
    "seed_verification_records",
    "seed_voice_channels",
    "temp_config_file",
]
