"""Tests for /check user activity-level tiers in the embed output.

Covers:
- Tier formatting helper renders all four dimensions correctly.
- Embed includes Activity Levels field when tiers are available.
- Embed omits Activity Levels field when metrics service is unavailable.
- _fetch_activity_tiers returns all-inactive when user has no data.
- _fetch_activity_tiers returns None on exception.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

from discord.ext import commands
import pytest

from cogs.admin.check_user import CheckUserCommands
from tests.factories import (
    FakeBot,
    FakeGuild,
    FakeInteraction,
    FakeMember,
    make_bot,
    make_guild,
    make_interaction,
    make_member,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_group(bot: Any | None = None) -> CheckUserCommands:
    """Instantiate the command group with a fake bot."""
    return CheckUserCommands(cast(commands.Bot, bot or make_bot()))


def _sample_tiers(
    combined: str = "regular",
    voice: str = "casual",
    chat: str = "hardcore",
    game: str = "inactive",
) -> dict[str, str]:
    return {
        "combined_tier": combined,
        "voice_tier": voice,
        "chat_tier": chat,
        "game_tier": game,
    }


# ---------------------------------------------------------------------------
# _format_activity_tiers
# ---------------------------------------------------------------------------


class TestFormatActivityTiers:
    """Unit tests for the tier formatting helper."""

    def test_all_tiers_rendered(self) -> None:
        group = _make_group()
        tiers = _sample_tiers()
        result = group._format_activity_tiers(tiers)

        assert "Combined" in result
        assert "Voice" in result
        assert "Text" in result
        assert "Gaming" in result

    def test_tier_labels_capitalised(self) -> None:
        group = _make_group()
        tiers = _sample_tiers(combined="hardcore", voice="regular", chat="casual", game="reserve")
        result = group._format_activity_tiers(tiers)

        assert "Hardcore" in result
        assert "Regular" in result
        assert "Casual" in result
        assert "Reserve" in result

    def test_inactive_uses_black_square(self) -> None:
        group = _make_group()
        tiers = _sample_tiers(combined="inactive", voice="inactive", chat="inactive", game="inactive")
        result = group._format_activity_tiers(tiers)

        assert result.count("⬛") == 4

    def test_emoji_mapping(self) -> None:
        group = _make_group()
        tiers = _sample_tiers(combined="hardcore", voice="regular", chat="casual", game="reserve")
        result = group._format_activity_tiers(tiers)

        assert "🔴" in result   # hardcore
        assert "🟠" in result   # regular
        assert "🔵" in result   # casual
        assert "⚪" in result   # reserve

    def test_missing_key_defaults_inactive(self) -> None:
        group = _make_group()
        result = group._format_activity_tiers({})  # no keys at all
        assert result.count("Inactive") == 4


# ---------------------------------------------------------------------------
# _build_user_embed — activity field presence
# ---------------------------------------------------------------------------


class TestBuildUserEmbedActivity:
    """Ensure the embed includes / omits the Activity Levels field correctly."""

    def _build(
        self,
        activity_tiers: dict[str, str] | None = None,
    ) -> Any:
        """Build an embed via the command group helper."""
        group = _make_group()
        member = make_member(user_id=42, name="Tester", display_name="Tester")
        requester = make_member(user_id=1, name="Admin", display_name="Admin")
        return group._build_user_embed(
            requester=cast(Any, requester),
            member=cast(Any, member),
            verification_row=None,
            target_sid="TEST",
            activity_tiers=activity_tiers,
        )

    def test_embed_includes_activity_field_when_tiers_present(self) -> None:
        embed = self._build(activity_tiers=_sample_tiers())
        field_names = [f.name for f in embed.fields]
        assert "Activity Levels (30d)" in field_names

    def test_embed_omits_activity_field_when_tiers_none(self) -> None:
        embed = self._build(activity_tiers=None)
        field_names = [f.name for f in embed.fields]
        assert "Activity Levels (30d)" not in field_names

    def test_activity_field_contains_all_dimensions(self) -> None:
        embed = self._build(activity_tiers=_sample_tiers())
        field = next(f for f in embed.fields if f.name == "Activity Levels (30d)")
        for label in ("Combined", "Voice", "Text", "Gaming"):
            assert label in field.value

    def test_existing_fields_preserved(self) -> None:
        """Adding activity tiers must not remove verification fields."""
        embed = self._build(activity_tiers=_sample_tiers())
        field_names = [f.name for f in embed.fields]
        for expected in ("Discord", "Verification Status", "RSI Handle"):
            assert expected in field_names


# ---------------------------------------------------------------------------
# _fetch_activity_tiers
# ---------------------------------------------------------------------------


class TestFetchActivityTiers:
    """Integration-style tests for the async tier fetcher."""

    @pytest.mark.asyncio
    async def test_returns_tiers_from_service(self) -> None:
        """Happy path: metrics service returns bucket data."""
        mock_metrics = AsyncMock()
        mock_metrics.get_member_activity_buckets = AsyncMock(
            return_value={
                42: {
                    "combined_tier": "regular",
                    "voice_tier": "casual",
                    "chat_tier": "hardcore",
                    "game_tier": "inactive",
                },
            },
        )
        bot = make_bot()
        bot.services = SimpleNamespace(metrics=mock_metrics)

        group = _make_group(bot)
        result = await group._fetch_activity_tiers(guild_id=100, user_id=42)

        assert result is not None
        assert result["combined_tier"] == "regular"
        assert result["voice_tier"] == "casual"
        assert result["chat_tier"] == "hardcore"
        assert result["game_tier"] == "inactive"

        mock_metrics.get_member_activity_buckets.assert_awaited_once_with(
            guild_id=100, user_ids=[42], lookback_days=30,
        )

    @pytest.mark.asyncio
    async def test_returns_all_inactive_when_no_data(self) -> None:
        """User not found in buckets → all inactive."""
        mock_metrics = AsyncMock()
        mock_metrics.get_member_activity_buckets = AsyncMock(return_value={})

        bot = make_bot()
        bot.services = SimpleNamespace(metrics=mock_metrics)

        group = _make_group(bot)
        result = await group._fetch_activity_tiers(guild_id=100, user_id=99)

        assert result is not None
        assert all(v == "inactive" for v in result.values())

    @pytest.mark.asyncio
    async def test_returns_none_when_no_metrics_service(self) -> None:
        """Bot has no metrics service → graceful None."""
        bot = make_bot()
        bot.services = SimpleNamespace()  # no .metrics attribute

        group = _make_group(bot)
        result = await group._fetch_activity_tiers(guild_id=100, user_id=42)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_services(self) -> None:
        """Bot has no services attribute at all → graceful None."""
        bot = make_bot()
        bot.services = None  # type: ignore[assignment]

        group = _make_group(bot)
        result = await group._fetch_activity_tiers(guild_id=100, user_id=42)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self) -> None:
        """Exception inside metrics service → graceful None, no crash."""
        mock_metrics = AsyncMock()
        mock_metrics.get_member_activity_buckets = AsyncMock(
            side_effect=RuntimeError("DB is gone"),
        )
        bot = make_bot()
        bot.services = SimpleNamespace(metrics=mock_metrics)

        group = _make_group(bot)
        result = await group._fetch_activity_tiers(guild_id=100, user_id=42)
        assert result is None
