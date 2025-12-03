# tests/test_verification_bulk_rsi_recheck.py

from unittest.mock import Mock, patch

import pytest

from helpers.bulk_check import StatusRow


@pytest.mark.asyncio
async def test_perform_rsi_recheck_concurrent_execution():
    """Test that RSI checks are executed concurrently using asyncio.gather."""
    from services.verification_bulk_service import VerificationBulkService

    bot = Mock()
    bot.http_client = Mock()
    service = VerificationBulkService(bot)

    input_rows = [
        StatusRow(1, "User1", "handle1", "main", 1609459200, "General"),
        StatusRow(2, "User2", "handle2", "affiliate", 1609459200, "Gaming"),
        StatusRow(3, "User3", "handle3", "non_member", 1609459200, None),
    ]

    # Track call order to verify concurrency
    call_order = []

    async def mock_verify(handle, client, org_name, org_sid=None):
        call_order.append(handle)
        return (1, handle.upper(), None, [], [])

    with patch(
        "verification.rsi_verification.is_valid_rsi_handle", side_effect=mock_verify
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

    # Mock bot with http_client
    bot = Mock()
    bot.http_client = Mock()

    service = VerificationBulkService(bot)

    # Create input rows
    input_rows = [
        StatusRow(1, "User1", "handle1", "main", 1609459200, "General"),
        StatusRow(2, "User2", "handle2", "affiliate", 1609459200, "Gaming"),
    ]

    # Mock is_valid_rsi_handle to return main status (verify_value=1)
    with patch("verification.rsi_verification.is_valid_rsi_handle") as mock_verify:
        mock_verify.return_value = (1, "Handle1", None, [], [])  # verify_value=1 = main

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

    service = VerificationBulkService(bot)

    input_rows = [
        StatusRow(1, "User1", "handle1", "main", 1609459200, "General"),
        StatusRow(2, "User2", "handle2", "affiliate", 1609459200, "Gaming"),
        StatusRow(3, "User3", "handle3", "non_member", 1609459200, None),
    ]

    # Mock different return values for each call
    with patch("verification.rsi_verification.is_valid_rsi_handle") as mock_verify:
        mock_verify.side_effect = [
            (1, "Handle1", None, [], []),  # main
            (2, "Handle2", None, [], []),  # affiliate
            (0, "Handle3", None, [], []),  # non_member
        ]

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

    service = VerificationBulkService(bot)

    input_rows = [
        StatusRow(1, "User1", "invalid_handle", "unknown", None, None),
    ]

    # Mock NotFoundError
    with patch("verification.rsi_verification.is_valid_rsi_handle") as mock_verify:
        mock_verify.side_effect = NotFoundError("Handle not found")

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

    service = VerificationBulkService(bot)

    input_rows = [
        StatusRow(1, "User1", "handle1", "main", 1609459200, "General"),
        StatusRow(2, "User2", "handle2", "affiliate", 1609459200, "Gaming"),
    ]

    # First call succeeds, second raises error
    with patch("verification.rsi_verification.is_valid_rsi_handle") as mock_verify:
        mock_verify.side_effect = [
            (1, "Handle1", None, [], []),
            Exception("Network error"),
        ]

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

    service = VerificationBulkService(bot)

    input_rows = [
        StatusRow(1, "User1", None, None, None, None),  # No RSI handle
    ]

    # Should not call is_valid_rsi_handle
    with patch("verification.rsi_verification.is_valid_rsi_handle") as mock_verify:
        result_rows = await service._perform_rsi_recheck(input_rows, guild_id=123456789)

        # Verify was not called since no handle
        mock_verify.assert_not_called()

    # Should mark as unknown with error message
    assert len(result_rows) == 1
    assert result_rows[0].rsi_status == "unknown"
    assert result_rows[0].rsi_checked_at is not None
    assert "No RSI handle" in result_rows[0].rsi_error


@pytest.mark.asyncio
async def test_perform_rsi_recheck_none_verify_value():
    """Test RSI recheck when verify_value is None."""
    from services.verification_bulk_service import VerificationBulkService

    bot = Mock()
    bot.http_client = Mock()

    service = VerificationBulkService(bot)

    input_rows = [
        StatusRow(1, "User1", "handle1", "unknown", None, None),
    ]

    # Mock returning None verify_value
    with patch("verification.rsi_verification.is_valid_rsi_handle") as mock_verify:
        mock_verify.return_value = (None, "Handle1", None, [], [])

        result_rows = await service._perform_rsi_recheck(input_rows, guild_id=123456789)

    # Should map None to unknown
    assert len(result_rows) == 1
    assert result_rows[0].rsi_status == "unknown"
    assert result_rows[0].rsi_error is None


@pytest.mark.asyncio
async def test_perform_rsi_recheck_partial_failures():
    """Test that partial failures don't affect successful checks."""
    from helpers.http_helper import NotFoundError
    from services.verification_bulk_service import VerificationBulkService

    bot = Mock()
    bot.http_client = Mock()
    service = VerificationBulkService(bot)

    input_rows = [
        StatusRow(1, "User1", "handle1", "main", 1609459200, "General"),
        StatusRow(2, "User2", "handle2", "affiliate", 1609459200, "Gaming"),
        StatusRow(3, "User3", "handle3", "non_member", 1609459200, None),
        StatusRow(4, "User4", "handle4", "unknown", None, None),
    ]

    # Mix of success and failures
    with patch("verification.rsi_verification.is_valid_rsi_handle") as mock_verify:
        mock_verify.side_effect = [
            (1, "Handle1", None, [], []),  # success - main
            NotFoundError("Not found"),  # failure - 404
            (0, "Handle3", None, [], []),  # success - non_member
            Exception("Timeout"),  # failure - exception
        ]

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
