from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import discord

from services.voice_channel_helpers import (
    classify_old_channel,
    get_member_count,
    get_user_game_name,
    sanitize_overwrite,
    validate_jtc_permissions,
)


def test_classify_old_channel_behavior() -> None:
    # Arrange
    occupied_count = 2
    empty_count = 0

    # Act
    occupied_action = classify_old_channel(occupied_count)
    empty_action = classify_old_channel(empty_count)

    # Assert
    assert occupied_action == "orphan"
    assert empty_action == "delete"


def test_get_member_count_prefers_live_channel_members() -> None:
    # Arrange
    logger = MagicMock()
    channel = cast(
        "discord.VoiceChannel",
        SimpleNamespace(id=123, members=[1, 2, 3]),
    )
    cache = {123: {10, 11}}

    # Act
    member_count = get_member_count(
        channel,
        bot=None,
        voice_channel_members=cache,
        logger=logger,
    )

    # Assert
    assert member_count == 3


def test_get_member_count_falls_back_to_cache() -> None:
    # Arrange
    logger = MagicMock()
    cache = {999: {1, 2, 3, 4}}

    # Act
    member_count = get_member_count(
        999,
        bot=None,
        voice_channel_members=cache,
        logger=logger,
    )

    # Assert
    assert member_count == 4


def test_sanitize_overwrite_masks_unavailable_allow_bits() -> None:
    # Arrange
    overwrite = discord.PermissionOverwrite(connect=True, manage_channels=True)
    bot_perms = discord.Permissions(connect=True)

    # Act
    sanitized = sanitize_overwrite(overwrite, bot_perms)

    # Assert
    allow, _deny = sanitized.pair()
    assert allow.connect is True
    assert allow.manage_channels is False


def test_get_user_game_name_returns_activity_name() -> None:
    # Arrange
    logger = MagicMock()
    member = cast(
        "discord.Member",
        SimpleNamespace(id=42, activity=SimpleNamespace(name="Star Citizen")),
    )

    # Act
    game_name = get_user_game_name(member, logger)

    # Assert
    assert game_name == "Star Citizen"


def test_validate_jtc_permissions_success() -> None:
    # Arrange
    logger = MagicMock()
    category_perms = discord.Permissions(
        view_channel=True,
        manage_channels=True,
        manage_roles=True,
    )
    guild_perms = discord.Permissions(move_members=True)

    bot_member = cast(
        "discord.Member", SimpleNamespace(guild_permissions=guild_perms)
    )
    guild = cast(
        "discord.Guild",
        SimpleNamespace(
        id=100,
        name="Test Guild",
        get_member=lambda _member_id: bot_member,
        ),
    )

    category = cast(
        "discord.CategoryChannel",
        SimpleNamespace(
            id=200,
            name="Join To Create",
            guild=guild,
            permissions_for=lambda _member: category_perms,
        ),
    )
    bot = cast("discord.Client", SimpleNamespace(user=SimpleNamespace(id=300)))

    # Act
    can_create, error = validate_jtc_permissions(category, bot=bot, logger=logger)

    # Assert
    assert can_create is True
    assert error is None


def test_validate_jtc_permissions_reports_missing_manage_channels() -> None:
    # Arrange
    logger = MagicMock()
    category_perms = discord.Permissions(
        view_channel=True,
        manage_channels=False,
        manage_roles=True,
    )
    guild_perms = discord.Permissions(move_members=True)

    bot_member = cast(
        "discord.Member", SimpleNamespace(guild_permissions=guild_perms)
    )
    guild = cast(
        "discord.Guild",
        SimpleNamespace(
        id=101,
        name="Test Guild",
        get_member=lambda _member_id: bot_member,
        ),
    )

    category = cast(
        "discord.CategoryChannel",
        SimpleNamespace(
            id=201,
            name="JTC",
            guild=guild,
            permissions_for=lambda _member: category_perms,
        ),
    )
    bot = cast("discord.Client", SimpleNamespace(user=SimpleNamespace(id=301)))

    # Act
    can_create, error = validate_jtc_permissions(category, bot=bot, logger=logger)

    # Assert
    assert can_create is False
    assert error == "Bot missing 'Manage Channels' permission in category 'JTC'"
