"""Tests for daily activity tracking and leadership summary features."""

from __future__ import annotations

import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from helpers.daily_activity_tracker import DailyActivityTracker
from helpers.leadership_log import EventType, InitiatorKind, InitiatorSource
from helpers.verification_logging import _has_meaningful_change, _track_daily_activity

# ---------------------------------------------------------------------------
# DailyActivityTracker unit tests
# ---------------------------------------------------------------------------


class TestDailyActivityTracker:
    """Test the in-memory tracker singleton."""

    def setup_method(self):
        DailyActivityTracker.reset_instance()

    def teardown_method(self):
        DailyActivityTracker.reset_instance()

    def test_singleton(self):
        a = DailyActivityTracker.get()
        b = DailyActivityTracker.get()
        assert a is b

    def test_reset_instance(self):
        a = DailyActivityTracker.get()
        DailyActivityTracker.reset_instance()
        b = DailyActivityTracker.get()
        assert a is not b

    def test_record_check_no_change(self):
        t = DailyActivityTracker.get()
        t.record_check(1, changed=False)
        data = t.peek(1)
        assert data["checked"] == 1
        assert data["changed"] == 0

    def test_record_check_with_change(self):
        t = DailyActivityTracker.get()
        t.record_check(1, changed=True)
        data = t.peek(1)
        assert data["checked"] == 1
        assert data["changed"] == 1

    def test_record_categories(self):
        t = DailyActivityTracker.get()
        t.record_first_time_manual(1)
        t.record_recheck(1)
        t.record_admin(1)
        data = t.peek(1)
        assert data["first_time_manual"] == 1
        assert data["recheck"] == 1
        assert data["admin"] == 1

    def test_snapshot_and_reset_clears_counters(self):
        t = DailyActivityTracker.get()
        t.record_check(1, changed=True)
        t.record_first_time_manual(1)

        snap = t.snapshot_and_reset()
        assert 1 in snap
        assert snap[1]["checked"] == 1
        assert snap[1]["changed"] == 1
        assert snap[1]["first_time_manual"] == 1

        # After reset, counters should be zero
        data = t.peek(1)
        assert data["checked"] == 0

    def test_snapshot_omits_zero_guilds(self):
        t = DailyActivityTracker.get()
        # Guild 1 has activity, guild 2 does not
        t.record_check(1)
        snap = t.snapshot_and_reset()
        assert 1 in snap
        assert 2 not in snap

    def test_multiple_guilds(self):
        t = DailyActivityTracker.get()
        t.record_check(100, changed=True)
        t.record_check(200, changed=False)
        t.record_admin(100)
        t.record_recheck(200)

        snap = t.snapshot_and_reset()
        assert snap[100]["checked"] == 1
        assert snap[100]["changed"] == 1
        assert snap[100]["admin"] == 1
        assert snap[200]["checked"] == 1
        assert snap[200]["changed"] == 0
        assert snap[200]["recheck"] == 1

    def test_accumulation(self):
        t = DailyActivityTracker.get()
        for _ in range(5):
            t.record_check(1, changed=True)
        for _ in range(3):
            t.record_check(1, changed=False)
        data = t.peek(1)
        assert data["checked"] == 8
        assert data["changed"] == 5


# ---------------------------------------------------------------------------
# _has_meaningful_change tests
# ---------------------------------------------------------------------------


class TestHasMeaningfulChange:
    def test_empty_diff_returns_false(self):
        assert _has_meaningful_change({}) is False
        assert _has_meaningful_change(None) is False  # type: ignore[arg-type]

    def test_same_values_returns_false(self):
        diff = {
            "status_before": "main",
            "status_after": "main",
            "moniker_before": "a",
            "moniker_after": "a",
            "handle_before": "h",
            "handle_after": "h",
        }
        assert _has_meaningful_change(diff) is False

    def test_status_change(self):
        diff = {"status_before": "non_member", "status_after": "main"}
        assert _has_meaningful_change(diff) is True

    def test_roles_added(self):
        diff = {"roles_added": ["role1"]}
        assert _has_meaningful_change(diff) is True

    def test_roles_removed(self):
        diff = {"roles_removed": ["role1"]}
        assert _has_meaningful_change(diff) is True

    def test_org_change(self):
        diff = {"main_orgs_before": ["A"], "main_orgs_after": ["B"]}
        assert _has_meaningful_change(diff) is True


# ---------------------------------------------------------------------------
# _track_daily_activity classification tests
# ---------------------------------------------------------------------------


class TestTrackDailyActivity:
    def setup_method(self):
        DailyActivityTracker.reset_instance()

    def teardown_method(self):
        DailyActivityTracker.reset_instance()

    def test_first_time_manual(self):
        _track_daily_activity(
            1,
            EventType.VERIFICATION,
            {"kind": InitiatorKind.USER, "source": InitiatorSource.BUTTON},
            {"status_before": None, "status_after": "main"},
        )
        data = DailyActivityTracker.get().peek(1)
        assert data["first_time_manual"] == 1
        assert data["checked"] == 1
        assert data["changed"] == 1

    def test_admin_action(self):
        _track_daily_activity(
            2,
            EventType.ADMIN_ACTION,
            {"kind": InitiatorKind.ADMIN, "source": InitiatorSource.COMMAND},
            {"status_before": "main", "status_after": "main"},
        )
        data = DailyActivityTracker.get().peek(2)
        assert data["admin"] == 1
        assert data["checked"] == 1
        assert data["changed"] == 0

    def test_auto_check_classified_as_recheck(self):
        _track_daily_activity(
            3,
            EventType.AUTO_CHECK,
            {"kind": InitiatorKind.AUTO},
            {"status_before": "main", "status_after": "main"},
        )
        data = DailyActivityTracker.get().peek(3)
        assert data["recheck"] == 1
        assert data["admin"] == 0
        assert data["first_time_manual"] == 0

    def test_user_recheck(self):
        _track_daily_activity(
            4,
            EventType.RECHECK,
            {"kind": InitiatorKind.USER, "source": InitiatorSource.BUTTON},
            {"status_before": "main", "status_after": "affiliate"},
        )
        data = DailyActivityTracker.get().peek(4)
        assert data["recheck"] == 1
        assert data["changed"] == 1

    def test_none_guild_id_is_skipped(self):
        _track_daily_activity(
            None,
            EventType.VERIFICATION,
            {"kind": InitiatorKind.USER},
            {"status_before": None, "status_after": "main"},
        )
        # No guild recorded
        snap = DailyActivityTracker.get().snapshot_and_reset()
        assert snap == {}

    def test_string_initiator_kind_admin(self):
        """Backward compat: kind may be passed as literal string."""
        _track_daily_activity(
            5,
            EventType.RECHECK,
            {"kind": "Admin"},
            {"status_before": "main", "status_after": "main"},
        )
        data = DailyActivityTracker.get().peek(5)
        assert data["admin"] == 1
        # Admin-triggered recheck also counts in recheck bucket
        assert data["recheck"] == 1

    def test_admin_recheck_counts_both_buckets(self):
        """Admin-triggered recheck should increment both admin and recheck."""
        _track_daily_activity(
            7,
            EventType.RECHECK,
            {"kind": InitiatorKind.ADMIN, "source": InitiatorSource.COMMAND},
            {"status_before": "main", "status_after": "main"},
        )
        data = DailyActivityTracker.get().peek(7)
        assert data["admin"] == 1
        assert data["recheck"] == 1
        assert data["checked"] == 1
        assert data["first_time_manual"] == 0

    def test_admin_action_no_recheck_bucket(self):
        """ADMIN_ACTION (non-recheck) should only increment admin, not recheck."""
        _track_daily_activity(
            8,
            EventType.ADMIN_ACTION,
            {"kind": InitiatorKind.ADMIN},
            {"status_before": "main", "status_after": "main"},
        )
        data = DailyActivityTracker.get().peek(8)
        assert data["admin"] == 1
        assert data["recheck"] == 0

    def test_empty_diff_counts_checked_but_not_changed(self):
        _track_daily_activity(
            6,
            EventType.AUTO_CHECK,
            {"kind": InitiatorKind.AUTO},
            None,
        )
        data = DailyActivityTracker.get().peek(6)
        assert data["checked"] == 1
        assert data["changed"] == 0


# ---------------------------------------------------------------------------
# Auto-check summary silence tests
# ---------------------------------------------------------------------------


class TestAutoCheckSummarySilence:
    """Test that _post_auto_summaries skips posting when changed == 0."""

    @pytest.mark.asyncio
    async def test_no_post_when_zero_changes(self):
        """When checked > 0 but changed == 0, no message should be sent."""
        from cogs.admin.recheck import AutoRecheck

        bot = types.SimpleNamespace(config={"auto_recheck": {"enabled": False}})
        cog = AutoRecheck(bot)  # type: ignore[arg-type]

        mock_channel = AsyncMock()

        with patch(
            "cogs.admin.recheck.resolve_leadership_channel",
            return_value=mock_channel,
        ):
            guild_summaries = {
                999: {"checked": 10, "changed": 0, "rows": []},
            }
            await cog._post_auto_summaries(guild_summaries)

        mock_channel.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_post_when_zero_checked(self):
        """When checked == 0, no message should be sent."""
        from cogs.admin.recheck import AutoRecheck

        bot = types.SimpleNamespace(config={"auto_recheck": {"enabled": False}})
        cog = AutoRecheck(bot)  # type: ignore[arg-type]

        mock_channel = AsyncMock()

        with patch(
            "cogs.admin.recheck.resolve_leadership_channel",
            return_value=mock_channel,
        ):
            guild_summaries = {
                999: {"checked": 0, "changed": 0, "rows": []},
            }
            await cog._post_auto_summaries(guild_summaries)

        mock_channel.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_posts_when_changes_exist(self):
        """When changed > 0, a message should be sent."""
        from cogs.admin.recheck import AutoRecheck

        bot = types.SimpleNamespace(config={"auto_recheck": {"enabled": False}})
        cog = AutoRecheck(bot)  # type: ignore[arg-type]

        mock_channel = AsyncMock()
        mock_channel.guild = types.SimpleNamespace(name="TestGuild")

        with patch(
            "cogs.admin.recheck.resolve_leadership_channel",
            return_value=mock_channel,
        ):
            guild_summaries = {
                999: {
                    "checked": 10,
                    "changed": 2,
                    "rows": [
                        {
                            "member": types.SimpleNamespace(id=1, display_name="u1"),
                            "diff": {
                                "status_before": "non_member",
                                "status_after": "main",
                            },
                        },
                        {
                            "member": types.SimpleNamespace(id=2, display_name="u2"),
                            "diff": {
                                "status_before": "affiliate",
                                "status_after": "main",
                            },
                        },
                    ],
                },
            }
            await cog._post_auto_summaries(guild_summaries)

        mock_channel.send.assert_called_once()
        call_kwargs = mock_channel.send.call_args
        assert "changes: 2" in call_kwargs[0][0]


# ---------------------------------------------------------------------------
# Daily leadership summary tests
# ---------------------------------------------------------------------------


class TestDailyLeadershipSummary:
    """Test _post_daily_leadership_summary on BulkAnnouncer."""

    def setup_method(self):
        DailyActivityTracker.reset_instance()

    def teardown_method(self):
        DailyActivityTracker.reset_instance()

    @pytest.mark.asyncio
    async def test_posts_summary_to_leadership_channel(self):
        from helpers.announcement import BulkAnnouncer

        # Seed tracker data
        tracker = DailyActivityTracker.get()
        tracker.record_check(100, changed=True)
        tracker.record_check(100, changed=False)
        tracker.record_first_time_manual(100)
        tracker.record_recheck(100)
        tracker.record_admin(100)

        mock_channel = AsyncMock()

        bot = MagicMock()
        bot.wait_until_ready = AsyncMock()

        with patch.object(BulkAnnouncer, "__init__", lambda self, b: None):
            announcer = BulkAnnouncer.__new__(BulkAnnouncer)
            announcer.bot = bot

        with patch(
            "helpers.announcement.resolve_leadership_channel",
            return_value=mock_channel,
        ):
            await announcer._post_daily_leadership_summary()

        mock_channel.send.assert_called_once()
        msg = mock_channel.send.call_args[0][0]
        assert "Daily Verification Summary" in msg
        assert "Checked: **2**" in msg
        assert "Changed: **1**" in msg
        assert "First-time verifications: **1**" in msg
        assert "Rechecks: **1**" in msg
        assert "Admin-triggered: **1**" in msg

    @pytest.mark.asyncio
    async def test_no_post_when_nothing_tracked(self):
        from helpers.announcement import BulkAnnouncer

        bot = MagicMock()
        bot.wait_until_ready = AsyncMock()

        with patch.object(BulkAnnouncer, "__init__", lambda self, b: None):
            announcer = BulkAnnouncer.__new__(BulkAnnouncer)
            announcer.bot = bot

        with patch(
            "helpers.announcement.resolve_leadership_channel",
        ) as mock_resolve:
            await announcer._post_daily_leadership_summary()

        mock_resolve.assert_not_called()

    @pytest.mark.asyncio
    async def test_resets_counters_after_post(self):
        from helpers.announcement import BulkAnnouncer

        tracker = DailyActivityTracker.get()
        tracker.record_check(100, changed=True)

        mock_channel = AsyncMock()

        bot = MagicMock()
        bot.wait_until_ready = AsyncMock()

        with patch.object(BulkAnnouncer, "__init__", lambda self, b: None):
            announcer = BulkAnnouncer.__new__(BulkAnnouncer)
            announcer.bot = bot

        with patch(
            "helpers.announcement.resolve_leadership_channel",
            return_value=mock_channel,
        ):
            await announcer._post_daily_leadership_summary()

        # Counters should be reset after posting
        data = tracker.peek(100)
        assert data["checked"] == 0
        assert data["changed"] == 0

    @pytest.mark.asyncio
    async def test_skips_guild_with_no_leadership_channel(self):
        from helpers.announcement import BulkAnnouncer

        tracker = DailyActivityTracker.get()
        tracker.record_check(100, changed=True)

        bot = MagicMock()
        bot.wait_until_ready = AsyncMock()

        with patch.object(BulkAnnouncer, "__init__", lambda self, b: None):
            announcer = BulkAnnouncer.__new__(BulkAnnouncer)
            announcer.bot = bot

        with patch(
            "helpers.announcement.resolve_leadership_channel",
            return_value=None,
        ):
            # Should not raise
            await announcer._post_daily_leadership_summary()

    @pytest.mark.asyncio
    async def test_handles_send_failure_gracefully(self):
        from helpers.announcement import BulkAnnouncer

        tracker = DailyActivityTracker.get()
        tracker.record_check(100, changed=True)

        mock_channel = AsyncMock()
        mock_channel.send.side_effect = Exception("Discord down")

        bot = MagicMock()
        bot.wait_until_ready = AsyncMock()

        with patch.object(BulkAnnouncer, "__init__", lambda self, b: None):
            announcer = BulkAnnouncer.__new__(BulkAnnouncer)
            announcer.bot = bot

        with patch(
            "helpers.announcement.resolve_leadership_channel",
            return_value=mock_channel,
        ):
            # Should not raise even on send failure
            await announcer._post_daily_leadership_summary()

        # Counters should still be reset (reset-on-flush policy)
        data = tracker.peek(100)
        assert data["checked"] == 0
        assert data["changed"] == 0
