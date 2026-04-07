# tests/test_verification_bulk_rsi_recheck.py
"""Tests for bulk verification RSI recheck using the unified pipeline."""

import time
from typing import cast
from unittest.mock import AsyncMock, Mock, patch

import pytest

from helpers.bulk_check import StatusRow
from services.verification_state import GlobalVerificationState, VerificationStatus


def _make_global_state(
    user_id: int, handle: str, status: VerificationStatus, error: str | None = None
):
    """Helper to create a GlobalVerificationState-like object."""
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


@pytest.mark.asyncio
async def test_perform_rsi_recheck_concurrent_execution():
    """Test that RSI checks are executed concurrently using asyncio.gather."""
    from services.verification_bulk_service import VerificationBulkService

    bot = Mock()
    bot.http_client = Mock()
    bot.config = {}
    service = VerificationBulkService(bot)

    input_rows = [
        StatusRow(1, "User1", "handle1", "main", 1609459200, "General"),
        StatusRow(2, "User2", "handle2", "affiliate", 1609459200, "Gaming"),
        StatusRow(3, "User3", "handle3", "non_member", 1609459200, None),
    ]

    # Track call order to verify concurrency
    call_order = []

    async def mock_compute(user_id, handle, http_client, **kwargs):
        call_order.append(handle)
        return _make_global_state(user_id, handle, "main")

    with (
        patch(
            "services.verification_state.compute_global_state", side_effect=mock_compute
        ),
        patch("services.verification_state.store_global_state", new_callable=AsyncMock),
        patch(
            "services.verification_scheduler.schedule_user_recheck",
            new_callable=AsyncMock,
        ),
    ):
        result_rows = await service._perform_rsi_recheck(input_rows, guild_id=123456789)

    # All handles should be checked
    assert len(call_order) == 3
    assert set(call_order) == {"handle1", "handle2", "handle3"}

    # All results should be populated
    assert len(result_rows) == 3
    assert all(row.rsi_status == "main" for row in result_rows)
    assert all(row.rsi_checked_at is not None for row in result_rows)


@pytest.mark.asyncio
async def test_perform_rsi_recheck_all_main():
    """Test RSI recheck when all users are main members."""
    from services.verification_bulk_service import VerificationBulkService

    bot = Mock()
    bot.http_client = Mock()
    bot.config = {}

    service = VerificationBulkService(bot)

    input_rows = [
        StatusRow(1, "User1", "handle1", "main", 1609459200, "General"),
        StatusRow(2, "User2", "handle2", "affiliate", 1609459200, "Gaming"),
    ]

    async def mock_compute(user_id, handle, http_client, **kwargs):
        return _make_global_state(user_id, handle, "main")

    with (
        patch(
            "services.verification_state.compute_global_state", side_effect=mock_compute
        ),
        patch("services.verification_state.store_global_state", new_callable=AsyncMock),
        patch(
            "services.verification_scheduler.schedule_user_recheck",
            new_callable=AsyncMock,
        ),
    ):
        result_rows = await service._perform_rsi_recheck(input_rows, guild_id=123456789)

    # Verify results
    assert len(result_rows) == 2
    assert result_rows[0].rsi_status == "main"
    assert result_rows[0].rsi_checked_at is not None
    assert result_rows[0].rsi_error is None
    assert result_rows[1].rsi_status == "main"
    assert result_rows[1].rsi_checked_at is not None
    assert result_rows[1].rsi_error is None


@pytest.mark.asyncio
async def test_perform_rsi_recheck_mixed_statuses():
    """Test RSI recheck with mixed membership statuses."""
    from services.verification_bulk_service import VerificationBulkService

    bot = Mock()
    bot.http_client = Mock()
    bot.config = {}

    service = VerificationBulkService(bot)

    input_rows = [
        StatusRow(1, "User1", "handle1", "main", 1609459200, "General"),
        StatusRow(2, "User2", "handle2", "affiliate", 1609459200, "Gaming"),
        StatusRow(3, "User3", "handle3", "non_member", 1609459200, None),
    ]

    # Return different statuses for each user
    statuses: dict[str, VerificationStatus] = {
        "handle1": cast("VerificationStatus", "main"),
        "handle2": cast("VerificationStatus", "affiliate"),
        "handle3": cast("VerificationStatus", "non_member"),
    }

    async def mock_compute(user_id, handle, http_client, **kwargs):
        return _make_global_state(user_id, handle, statuses[handle])

    with (
        patch(
            "services.verification_state.compute_global_state", side_effect=mock_compute
        ),
        patch("services.verification_state.store_global_state", new_callable=AsyncMock),
        patch(
            "services.verification_scheduler.schedule_user_recheck",
            new_callable=AsyncMock,
        ),
    ):
        result_rows = await service._perform_rsi_recheck(input_rows, guild_id=123456789)

    # Verify results map correctly
    assert len(result_rows) == 3
    assert result_rows[0].rsi_status == "main"
    assert result_rows[0].rsi_error is None
    assert result_rows[1].rsi_status == "affiliate"
    assert result_rows[1].rsi_error is None
    assert result_rows[2].rsi_status == "non_member"
    assert result_rows[2].rsi_error is None


@pytest.mark.asyncio
async def test_perform_rsi_recheck_not_found():
    """Test RSI recheck when handle is not found (404)."""
    from helpers.http_helper import NotFoundError
    from services.verification_bulk_service import VerificationBulkService

    bot = Mock()
    bot.http_client = Mock()
    bot.config = {}

    service = VerificationBulkService(bot)

    input_rows = [
        StatusRow(1, "User1", "invalid_handle", "unknown", None, None),
    ]

    async def mock_compute(user_id, handle, http_client, **kwargs):
        raise NotFoundError("Handle not found")

    with (
        patch(
            "services.verification_state.compute_global_state", side_effect=mock_compute
        ),
        patch("services.verification_state.store_global_state", new_callable=AsyncMock),
        patch(
            "services.verification_scheduler.schedule_user_recheck",
            new_callable=AsyncMock,
        ),
    ):
        result_rows = await service._perform_rsi_recheck(input_rows, guild_id=123456789)

    # Should handle gracefully and mark as unknown
    assert len(result_rows) == 1
    assert result_rows[0].rsi_status == "unknown"
    assert result_rows[0].rsi_checked_at is not None
    assert "not found" in result_rows[0].rsi_error.lower()


@pytest.mark.asyncio
async def test_perform_rsi_recheck_generic_error():
    """Test RSI recheck resilience to generic errors."""
    from services.verification_bulk_service import VerificationBulkService

    bot = Mock()
    bot.http_client = Mock()
    bot.config = {}

    service = VerificationBulkService(bot)

    input_rows = [
        StatusRow(1, "User1", "handle1", "main", 1609459200, "General"),
        StatusRow(2, "User2", "handle2", "affiliate", 1609459200, "Gaming"),
    ]

    call_count = [0]

    async def mock_compute(user_id, handle, http_client, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return _make_global_state(user_id, handle, "main")
        raise Exception("Network error")

    with (
        patch(
            "services.verification_state.compute_global_state", side_effect=mock_compute
        ),
        patch("services.verification_state.store_global_state", new_callable=AsyncMock),
        patch(
            "services.verification_scheduler.schedule_user_recheck",
            new_callable=AsyncMock,
        ),
    ):
        result_rows = await service._perform_rsi_recheck(input_rows, guild_id=123456789)

    # First should succeed, second should be marked unknown with error
    assert len(result_rows) == 2
    assert result_rows[0].rsi_status == "main"
    assert result_rows[0].rsi_error is None
    assert result_rows[1].rsi_status == "unknown"
    assert "Network error" in result_rows[1].rsi_error


@pytest.mark.asyncio
async def test_perform_rsi_recheck_no_handle():
    """Test RSI recheck when user has no RSI handle."""
    from services.verification_bulk_service import VerificationBulkService

    bot = Mock()
    bot.http_client = Mock()
    bot.config = {}

    service = VerificationBulkService(bot)

    input_rows = [
        StatusRow(1, "User1", None, None, None, None),  # No RSI handle
    ]

    compute_called = [False]

    async def mock_compute(user_id, handle, http_client, **kwargs):
        compute_called[0] = True
        return _make_global_state(user_id, handle, "main")

    with (
        patch(
            "services.verification_state.compute_global_state", side_effect=mock_compute
        ),
        patch("services.verification_state.store_global_state", new_callable=AsyncMock),
        patch(
            "services.verification_scheduler.schedule_user_recheck",
            new_callable=AsyncMock,
        ),
    ):
        result_rows = await service._perform_rsi_recheck(input_rows, guild_id=123456789)

    # compute_global_state should not be called since no handle
    assert not compute_called[0]

    # Should mark as unknown with error message
    assert len(result_rows) == 1
    assert result_rows[0].rsi_status == "unknown"
    assert result_rows[0].rsi_checked_at is not None
    assert "No RSI handle" in result_rows[0].rsi_error


@pytest.mark.asyncio
async def test_perform_rsi_recheck_with_error_in_state():
    """Test RSI recheck when compute_global_state returns error in state."""
    from services.verification_bulk_service import VerificationBulkService

    bot = Mock()
    bot.http_client = Mock()
    bot.config = {}

    service = VerificationBulkService(bot)

    input_rows = [
        StatusRow(1, "User1", "handle1", "unknown", None, None),
    ]

    async def mock_compute(user_id, handle, http_client, **kwargs):
        return _make_global_state(
            user_id, handle, "non_member", error="RSI fetch failed"
        )

    with (
        patch(
            "services.verification_state.compute_global_state", side_effect=mock_compute
        ),
        patch("services.verification_state.store_global_state", new_callable=AsyncMock),
        patch(
            "services.verification_scheduler.schedule_user_recheck",
            new_callable=AsyncMock,
        ),
    ):
        result_rows = await service._perform_rsi_recheck(input_rows, guild_id=123456789)

    # Should return the state but include the error
    assert len(result_rows) == 1
    assert result_rows[0].rsi_status == "non_member"
    assert result_rows[0].rsi_error == "RSI fetch failed"


@pytest.mark.asyncio
async def test_perform_rsi_recheck_partial_failures():
    """Test that partial failures don't affect successful checks."""
    from helpers.http_helper import NotFoundError
    from services.verification_bulk_service import VerificationBulkService

    bot = Mock()
    bot.http_client = Mock()
    bot.config = {}
    service = VerificationBulkService(bot)

    input_rows = [
        StatusRow(1, "User1", "handle1", "main", 1609459200, "General"),
        StatusRow(2, "User2", "handle2", "affiliate", 1609459200, "Gaming"),
        StatusRow(3, "User3", "handle3", "non_member", 1609459200, None),
        StatusRow(4, "User4", "handle4", "unknown", None, None),
    ]

    responses = {
        "handle1": (cast("VerificationStatus", "main"), None),
        "handle2": (cast("VerificationStatus", "404"), NotFoundError("Not found")),
        "handle3": (cast("VerificationStatus", "non_member"), None),
        "handle4": (cast("VerificationStatus", "error"), Exception("Timeout")),
    }

    async def mock_compute(user_id, handle, http_client, **kwargs):
        status, error = responses[handle]
        if error:
            raise error
        return _make_global_state(user_id, handle, cast("VerificationStatus", status))

    with (
        patch(
            "services.verification_state.compute_global_state", side_effect=mock_compute
        ),
        patch("services.verification_state.store_global_state", new_callable=AsyncMock),
        patch(
            "services.verification_scheduler.schedule_user_recheck",
            new_callable=AsyncMock,
        ),
    ):
        result_rows = await service._perform_rsi_recheck(input_rows, guild_id=123456789)

    # Verify mixed results
    assert len(result_rows) == 4
    assert result_rows[0].rsi_status == "main"
    assert result_rows[0].rsi_error is None
    assert result_rows[1].rsi_status == "unknown"
    assert "not found" in result_rows[1].rsi_error.lower()
    assert result_rows[2].rsi_status == "non_member"
    assert result_rows[2].rsi_error is None
    assert result_rows[3].rsi_status == "unknown"
    assert "Timeout" in result_rows[3].rsi_error


# ---------------------------------------------------------------------------
# Guild sync integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_guild_sync_called_on_successful_recheck() -> None:
    """Verify sync_user_to_all_guilds is called when compute succeeds (no error)."""
    from services.verification_bulk_service import VerificationBulkService

    bot = Mock()
    bot.http_client = Mock()
    bot.config = {}
    service = VerificationBulkService(bot)

    input_rows = [
        StatusRow(1, "User1", "handle1", "main", 1609459200, "General"),
    ]

    async def mock_compute(
        user_id: int, handle: str, http_client: object, **kwargs: object
    ) -> GlobalVerificationState:
        return _make_global_state(user_id, handle, "main")

    mock_sync = AsyncMock(return_value=[])

    with (
        patch(
            "services.verification_state.compute_global_state", side_effect=mock_compute
        ),
        patch("services.verification_state.store_global_state", new_callable=AsyncMock),
        patch(
            "services.verification_scheduler.schedule_user_recheck",
            new_callable=AsyncMock,
        ),
        patch("services.guild_sync.sync_user_to_all_guilds", mock_sync),
    ):
        await service._perform_rsi_recheck(input_rows, guild_id=123456789)

    # sync_user_to_all_guilds must have been called for the successful user
    mock_sync.assert_awaited_once()
    call_args = mock_sync.call_args
    assert call_args[0][0].user_id == 1  # global_state
    assert call_args[0][1] is bot  # bot instance


@pytest.mark.asyncio
async def test_guild_sync_not_called_on_error_state() -> None:
    """Verify sync_user_to_all_guilds is NOT called when compute returns an error."""
    from services.verification_bulk_service import VerificationBulkService

    bot = Mock()
    bot.http_client = Mock()
    bot.config = {}
    service = VerificationBulkService(bot)

    input_rows = [
        StatusRow(1, "User1", "handle1", "main", 1609459200, "General"),
    ]

    async def mock_compute(
        user_id: int, handle: str, http_client: object, **kwargs: object
    ) -> GlobalVerificationState:
        return _make_global_state(
            user_id, handle, "non_member", error="RSI fetch failed"
        )

    mock_sync = AsyncMock(return_value=[])

    with (
        patch(
            "services.verification_state.compute_global_state", side_effect=mock_compute
        ),
        patch("services.verification_state.store_global_state", new_callable=AsyncMock),
        patch(
            "services.verification_scheduler.schedule_user_recheck",
            new_callable=AsyncMock,
        ),
        patch("services.guild_sync.sync_user_to_all_guilds", mock_sync),
        patch(
            "services.db.database.Database.get_auto_recheck_fail_count",
            new_callable=AsyncMock,
            return_value=0,
        ),
        patch(
            "services.verification_scheduler.handle_recheck_failure",
            new_callable=AsyncMock,
        ),
    ):
        await service._perform_rsi_recheck(input_rows, guild_id=123456789)

    mock_sync.assert_not_awaited()


# ---------------------------------------------------------------------------
# Error state persistence guard tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_not_called_on_error_state() -> None:
    """Verify store_global_state is NOT called when compute returns an error."""
    from services.verification_bulk_service import VerificationBulkService

    bot = Mock()
    bot.http_client = Mock()
    bot.config = {}
    service = VerificationBulkService(bot)

    input_rows = [
        StatusRow(1, "User1", "handle1", "main", 1609459200, "General"),
    ]

    async def mock_compute(
        user_id: int, handle: str, http_client: object, **kwargs: object
    ) -> GlobalVerificationState:
        return _make_global_state(
            user_id, handle, "non_member", error="RSI fetch failed"
        )

    mock_store = AsyncMock()

    with (
        patch(
            "services.verification_state.compute_global_state", side_effect=mock_compute
        ),
        patch("services.verification_state.store_global_state", mock_store),
        patch(
            "services.verification_scheduler.schedule_user_recheck",
            new_callable=AsyncMock,
        ),
        patch("services.guild_sync.sync_user_to_all_guilds", new_callable=AsyncMock),
        patch(
            "services.db.database.Database.get_auto_recheck_fail_count",
            new_callable=AsyncMock,
            return_value=0,
        ),
        patch(
            "services.verification_scheduler.handle_recheck_failure",
            new_callable=AsyncMock,
        ),
    ):
        await service._perform_rsi_recheck(input_rows, guild_id=123456789)

    # store_global_state must NOT have been called since error was set
    mock_store.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_recheck_failure_called_on_error_state() -> None:
    """Verify handle_recheck_failure IS called when compute returns an error."""
    from services.verification_bulk_service import VerificationBulkService

    bot = Mock()
    bot.http_client = Mock()
    bot.config = {}
    service = VerificationBulkService(bot)

    input_rows = [
        StatusRow(1, "User1", "handle1", "main", 1609459200, "General"),
    ]

    async def mock_compute(
        user_id: int, handle: str, http_client: object, **kwargs: object
    ) -> GlobalVerificationState:
        return _make_global_state(user_id, handle, "non_member", error="RSI is down")

    mock_handle_failure = AsyncMock()

    with (
        patch(
            "services.verification_state.compute_global_state", side_effect=mock_compute
        ),
        patch("services.verification_state.store_global_state", new_callable=AsyncMock),
        patch(
            "services.verification_scheduler.schedule_user_recheck",
            new_callable=AsyncMock,
        ),
        patch("services.guild_sync.sync_user_to_all_guilds", new_callable=AsyncMock),
        patch(
            "services.db.database.Database.get_auto_recheck_fail_count",
            new_callable=AsyncMock,
            return_value=2,
        ),
        patch(
            "services.verification_scheduler.handle_recheck_failure",
            mock_handle_failure,
        ),
    ):
        await service._perform_rsi_recheck(input_rows, guild_id=123456789)

    mock_handle_failure.assert_awaited_once()
    call_kwargs = mock_handle_failure.call_args
    assert call_kwargs[0][0] == 1  # user_id
    assert "RSI is down" in call_kwargs[0][1]  # error message
    assert call_kwargs[1]["fail_count"] == 3  # incremented from 2


@pytest.mark.asyncio
async def test_store_called_on_successful_recheck() -> None:
    """Verify store_global_state IS called when compute succeeds (no error)."""
    from services.verification_bulk_service import VerificationBulkService

    bot = Mock()
    bot.http_client = Mock()
    bot.config = {}
    service = VerificationBulkService(bot)

    input_rows = [
        StatusRow(1, "User1", "handle1", "affiliate", 1609459200, "General"),
    ]

    async def mock_compute(
        user_id: int, handle: str, http_client: object, **kwargs: object
    ) -> GlobalVerificationState:
        return _make_global_state(user_id, handle, "affiliate")

    mock_store = AsyncMock()

    with (
        patch(
            "services.verification_state.compute_global_state", side_effect=mock_compute
        ),
        patch("services.verification_state.store_global_state", mock_store),
        patch(
            "services.verification_scheduler.schedule_user_recheck",
            new_callable=AsyncMock,
        ),
        patch("services.guild_sync.sync_user_to_all_guilds", new_callable=AsyncMock),
    ):
        await service._perform_rsi_recheck(input_rows, guild_id=123456789)

    mock_store.assert_awaited_once()
    stored_state = mock_store.call_args[0][0]
    assert stored_state.user_id == 1
    assert stored_state.status == "affiliate"
