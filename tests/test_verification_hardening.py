# tests/test_verification_hardening.py
"""Regression tests for verification flow hardening (Phases 3–6).

Covers:
- Bulk pipeline guild sync integration
- Error state persistence guard
- Scheduler jitter floor
- RSI parser SID extraction hardening
"""

import time
from unittest.mock import AsyncMock, Mock, patch

import pytest

from helpers.bulk_check import StatusRow
from services.verification_state import GlobalVerificationState, VerificationStatus


def _make_global_state(
    user_id: int,
    handle: str,
    status: VerificationStatus,
    error: str | None = None,
) -> GlobalVerificationState:
    main_orgs = ["TEST"] if status == "main" else []
    affiliate_orgs = ["TEST"] if status == "affiliate" else []
    return GlobalVerificationState(
        user_id=user_id,
        rsi_handle=handle.upper(),
        status=status,
        main_orgs=main_orgs,
        affiliate_orgs=affiliate_orgs,
        community_moniker=None,
        checked_at=int(time.time()),
        error=error,
    )


# --- Phase 3: Bulk pipeline guild sync ---


@pytest.mark.asyncio
async def test_bulk_recheck_calls_guild_sync_on_success() -> None:
    """Bulk pipeline must call sync_user_to_all_guilds after successful compute."""
    from services.verification_bulk_service import VerificationBulkService

    bot = Mock()
    bot.http_client = Mock()
    bot.config = {}
    service = VerificationBulkService(bot)

    input_rows = [
        StatusRow(1, "User1", "handle1", "main", 1609459200, "General"),
    ]

    mock_sync = AsyncMock(return_value=[])

    async def mock_compute(user_id, handle, http_client, **kwargs):
        return _make_global_state(user_id, handle, "affiliate")

    with (
        patch(
            "services.verification_state.compute_global_state",
            side_effect=mock_compute,
        ),
        patch(
            "services.verification_state.store_global_state",
            new_callable=AsyncMock,
        ),
        patch(
            "services.verification_scheduler.schedule_user_recheck",
            new_callable=AsyncMock,
        ),
        patch(
            "services.guild_sync.sync_user_to_all_guilds",
            mock_sync,
        ),
    ):
        result_rows = await service._perform_rsi_recheck(input_rows, guild_id=123)

    # sync_user_to_all_guilds must have been called
    assert mock_sync.call_count == 1
    call_args = mock_sync.call_args
    assert call_args[0][0].status == "affiliate"  # global_state
    assert call_args[0][1] is bot  # bot reference

    assert len(result_rows) == 1
    assert result_rows[0].rsi_status == "affiliate"


@pytest.mark.asyncio
async def test_bulk_recheck_skips_sync_on_error_state() -> None:
    """Bulk pipeline must NOT call guild sync when compute returns error state."""
    from services.verification_bulk_service import VerificationBulkService

    bot = Mock()
    bot.http_client = Mock()
    bot.config = {}
    service = VerificationBulkService(bot)

    input_rows = [
        StatusRow(1, "User1", "handle1", "main", 1609459200, "General"),
    ]

    mock_sync = AsyncMock(return_value=[])
    mock_store = AsyncMock()

    async def mock_compute(user_id, handle, http_client, **kwargs):
        return _make_global_state(
            user_id, handle, "non_member", error="RSI fetch failed"
        )

    with (
        patch(
            "services.verification_state.compute_global_state",
            side_effect=mock_compute,
        ),
        patch(
            "services.verification_state.store_global_state",
            mock_store,
        ),
        patch(
            "services.verification_scheduler.schedule_user_recheck",
            new_callable=AsyncMock,
        ),
        patch(
            "services.verification_scheduler.handle_recheck_failure",
            new_callable=AsyncMock,
        ),
        patch(
            "services.guild_sync.sync_user_to_all_guilds",
            mock_sync,
        ),
        patch(
            "services.db.database.Database.get_auto_recheck_fail_count",
            new_callable=AsyncMock,
            return_value=0,
        ),
    ):
        result_rows = await service._perform_rsi_recheck(input_rows, guild_id=123)

    # Guild sync must NOT be called for error states
    mock_sync.assert_not_called()
    # store_global_state must NOT be called for error states
    mock_store.assert_not_called()

    assert len(result_rows) == 1
    assert result_rows[0].rsi_error == "RSI fetch failed"


@pytest.mark.asyncio
async def test_bulk_recheck_calls_handle_recheck_failure_on_error() -> None:
    """Bulk pipeline must call handle_recheck_failure for error states."""
    from services.verification_bulk_service import VerificationBulkService

    bot = Mock()
    bot.http_client = Mock()
    bot.config = {}
    service = VerificationBulkService(bot)

    input_rows = [
        StatusRow(1, "User1", "handle1", "main", 1609459200, "General"),
    ]

    mock_failure = AsyncMock()

    async def mock_compute(user_id, handle, http_client, **kwargs):
        return _make_global_state(
            user_id, handle, "non_member", error="RSI service down"
        )

    with (
        patch(
            "services.verification_state.compute_global_state",
            side_effect=mock_compute,
        ),
        patch(
            "services.verification_state.store_global_state",
            new_callable=AsyncMock,
        ),
        patch(
            "services.verification_scheduler.schedule_user_recheck",
            new_callable=AsyncMock,
        ),
        patch(
            "services.verification_scheduler.handle_recheck_failure",
            mock_failure,
        ),
        patch(
            "services.guild_sync.sync_user_to_all_guilds",
            new_callable=AsyncMock,
        ),
        patch(
            "services.db.database.Database.get_auto_recheck_fail_count",
            new_callable=AsyncMock,
            return_value=2,
        ),
    ):
        await service._perform_rsi_recheck(input_rows, guild_id=123)

    mock_failure.assert_called_once()
    call_kwargs = mock_failure.call_args
    assert call_kwargs[0][0] == 1  # user_id
    assert "RSI service down" in call_kwargs[0][1]  # error message
    assert call_kwargs[1]["fail_count"] == 3  # incremented


# --- Phase 5: Error state persistence guard ---


@pytest.mark.asyncio
async def test_store_global_state_rejects_error_state() -> None:
    """store_global_state must refuse to persist a state with an error."""
    from services.verification_state import store_global_state

    error_state = _make_global_state(1, "handle", "non_member", error="fetch failed")

    with pytest.raises(RuntimeError, match="Refusing to persist error state"):
        await store_global_state(error_state)


# --- Phase 6: Scheduler jitter floor ---


def test_compute_next_retry_always_future() -> None:
    """compute_next_retry must always return a timestamp in the future."""
    from services.verification_scheduler import compute_next_retry

    state = _make_global_state(1, "handle", "non_member")

    # Even with extreme negative jitter, result should be at least now + 1h
    with patch("services.verification_scheduler._get_jitter", return_value=-999999):
        result = compute_next_retry(state, config=None)

    now = int(time.time())
    assert result >= now + 3600  # At least 1 hour in the future


def test_compute_next_retry_normal_case() -> None:
    """compute_next_retry should add cadence days + jitter normally."""
    from services.verification_scheduler import compute_next_retry

    state = _make_global_state(1, "handle", "main")

    with patch("services.verification_scheduler._get_jitter", return_value=0):
        result = compute_next_retry(state, config=None)

    now = int(time.time())
    # Main cadence is 14 days
    expected = now + 14 * 86400
    assert abs(result - expected) < 5  # Within 5 seconds tolerance


# --- Phase 4: RSI parser SID extraction ---


def test_parse_rsi_org_sids_main_reordered_entries() -> None:
    """Main org parser should find SID even when entries are reordered."""
    from verification.rsi_verification import parse_rsi_org_sids

    html = """
    <div class="box-content org main">
        <p class="entry">
            <span class="label">Members</span>
            <strong class="value">42</strong>
        </p>
        <p class="entry">
            <span class="label">Spectrum Identification (SID)</span>
            <strong class="value">TESTSQUAD</strong>
        </p>
    </div>
    """
    result = parse_rsi_org_sids(html)
    assert result["main_orgs"] == ["TESTSQUAD"]


def test_parse_rsi_org_sids_affiliate_whitespace_sid() -> None:
    """Affiliate parser should treat whitespace-only SID as REDACTED."""
    from verification.rsi_verification import parse_rsi_org_sids

    html = """
    <div class="box-content org affiliation">
        <p class="entry">
            <span class="label">Spectrum Identification (SID)</span>
            <strong class="value">   </strong>
        </p>
    </div>
    """
    result = parse_rsi_org_sids(html)
    assert result["affiliate_orgs"] == ["REDACTED"]


def test_parse_rsi_org_sids_affiliate_nbsp_sid() -> None:
    """Affiliate parser should treat nbsp SID as REDACTED."""
    from verification.rsi_verification import parse_rsi_org_sids

    html = """
    <div class="box-content org affiliation">
        <p class="entry">
            <span class="label">SID</span>
            <strong class="value">\xa0</strong>
        </p>
    </div>
    """
    result = parse_rsi_org_sids(html)
    assert result["affiliate_orgs"] == ["REDACTED"]


def test_parse_rsi_org_sids_main_no_sid_label() -> None:
    """Main org with entries but no SID label should be REDACTED."""
    from verification.rsi_verification import parse_rsi_org_sids

    html = """
    <div class="box-content org main">
        <p class="entry">
            <span class="label">Members</span>
            <strong class="value">100</strong>
        </p>
    </div>
    """
    result = parse_rsi_org_sids(html)
    assert result["main_orgs"] == ["REDACTED"]


def test_parse_rsi_org_sids_valid_affiliate() -> None:
    """Affiliate with valid SID should be extracted correctly."""
    from verification.rsi_verification import parse_rsi_org_sids

    html = """
    <div class="box-content org affiliation">
        <p class="entry">
            <span class="label">Spectrum Identification (SID)</span>
            <strong class="value">AVOCADO</strong>
        </p>
    </div>
    """
    result = parse_rsi_org_sids(html)
    assert result["affiliate_orgs"] == ["AVOCADO"]
