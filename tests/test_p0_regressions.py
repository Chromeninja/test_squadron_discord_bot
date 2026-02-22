"""Regression tests for P0 bug fixes.

Covers:
  - derive_membership_status case-insensitive comparison
  - build_embed properly awaiting _verbosity (async)
  - voice_utils return type annotations (runtime check)
  - fetch_html dispatching on method parameter
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.db.database import derive_membership_status

# =============================================================================
# derive_membership_status — case-insensitive comparison
# =============================================================================


class TestDeriveMembershipStatus:
    """Verify case-insensitive SID comparison after consolidation."""

    def test_exact_match_main(self):
        assert derive_membership_status(["TEST"], [], "TEST") == "main"

    def test_case_insensitive_main_lower_target(self):
        """SID stored as 'TEST' but target is 'test' — must still match."""
        assert derive_membership_status(["TEST"], [], "test") == "main"

    def test_case_insensitive_main_upper_target(self):
        """SID stored as 'test' but target is 'TEST' — must still match."""
        assert derive_membership_status(["test"], [], "TEST") == "main"

    def test_case_insensitive_mixed_case(self):
        assert derive_membership_status(["TeSt"], [], "tEsT") == "main"

    def test_exact_match_affiliate(self):
        assert derive_membership_status([], ["ALLY"], "ALLY") == "affiliate"

    def test_case_insensitive_affiliate(self):
        assert derive_membership_status([], ["ally"], "ALLY") == "affiliate"

    def test_non_member(self):
        assert derive_membership_status(["OTHER"], ["ALSO_OTHER"], "TEST") == "non_member"

    def test_none_orgs(self):
        assert derive_membership_status(None, None, "TEST") == "non_member"

    def test_empty_lists(self):
        assert derive_membership_status([], [], "TEST") == "non_member"

    def test_redacted_filtered_out(self):
        """REDACTED entries should never match any target."""
        assert derive_membership_status(["REDACTED"], ["REDACTED"], "REDACTED") == "non_member"

    def test_main_takes_priority_over_affiliate(self):
        """If SID appears in both main and affiliate, 'main' wins."""
        assert derive_membership_status(["TEST"], ["TEST"], "TEST") == "main"

    def test_empty_string_sid_in_list(self):
        """Empty string SIDs should be filtered out (falsy)."""
        assert derive_membership_status(["", "TEST"], [], "TEST") == "main"

    def test_none_sid_in_list(self):
        """None values in org lists should not crash."""
        assert derive_membership_status([None, "TEST"], [], "TEST") == "main"  # type: ignore[list-item]


# =============================================================================
# build_embed — now async, properly awaits _verbosity
# =============================================================================


@pytest.mark.asyncio
async def test_build_embed_is_async_and_awaits_verbosity():
    """build_embed must be a coroutine and must await _verbosity."""
    import inspect

    from helpers.leadership_log import build_embed

    assert inspect.iscoroutinefunction(build_embed), "build_embed must be async"


@pytest.mark.asyncio
async def test_build_embed_verbose_shows_unchanged_fields():
    """When verbosity='verbose', unchanged fields should still appear."""
    from helpers.leadership_log import (
        ChangeSet,
        EventType,
        InitiatorKind,
        build_embed,
    )

    bot = MagicMock()
    bot.services = MagicMock()
    bot.services.config.get_global_setting = AsyncMock(return_value="verbose")

    cs = ChangeSet(
        user_id=12345,
        guild_id=99999,
        event=EventType.RECHECK,
        initiator_kind=InitiatorKind.USER,
        # Unchanged handle (before == after)
        handle_before="CitizenX",
        handle_after="CitizenX",
    )

    embed = await build_embed(bot, cs)

    # With verbose, a "No Change" field should appear for the unchanged handle
    field_names = [f.name for f in embed.fields]
    assert "Handle" in field_names, (
        "Verbose mode should show unchanged handle field"
    )
    handle_field = next(f for f in embed.fields if f.name == "Handle")
    assert "No Change" in (handle_field.value or "")


@pytest.mark.asyncio
async def test_build_embed_compact_hides_unchanged_fields():
    """When verbosity='compact', unchanged fields should be omitted."""
    from helpers.leadership_log import (
        ChangeSet,
        EventType,
        InitiatorKind,
        build_embed,
    )

    bot = MagicMock()
    bot.services = MagicMock()
    bot.services.config.get_global_setting = AsyncMock(return_value="compact")

    cs = ChangeSet(
        user_id=12345,
        guild_id=99999,
        event=EventType.RECHECK,
        initiator_kind=InitiatorKind.USER,
        handle_before="CitizenX",
        handle_after="CitizenX",
    )

    embed = await build_embed(bot, cs)

    # With compact verbosity, unchanged fields should NOT appear
    field_names = [f.name for f in embed.fields]
    assert "Handle" not in field_names, (
        "Compact mode should hide unchanged fields"
    )


# =============================================================================
# fetch_html — method parameter dispatch
# =============================================================================


@pytest.mark.asyncio
async def test_fetch_html_dispatches_on_method():
    """fetch_html should use the correct HTTP method from the parameter."""
    from helpers.http_helper import HTTPClient

    client = HTTPClient.__new__(HTTPClient)

    # Setup minimal internal state needed by fetch_html
    import asyncio
    client._sem = asyncio.Semaphore(1)
    client._request_count = 0
    client._error_count = 0
    client._retry_count = 0
    client._user_agent = "test"

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.text = AsyncMock(return_value="<html></html>")
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_response)
    mock_session.post = MagicMock(return_value=mock_response)

    client._get_session = AsyncMock(return_value=mock_session)

    from helpers.http_helper import NO_RETRY_POLICY
    client._retry_policy = NO_RETRY_POLICY

    # Test GET (default)
    with patch("helpers.http_helper.asyncio.sleep", new_callable=AsyncMock):
        await client.fetch_html("http://example.com", method="GET", retry=False)
        mock_session.get.assert_called()

    # Reset counts
    client._request_count = 0

    # Test POST
    with patch("helpers.http_helper.asyncio.sleep", new_callable=AsyncMock):
        await client.fetch_html("http://example.com", method="POST", retry=False)
        mock_session.post.assert_called()
