"""
Tests for TicketService — category CRUD, ticket lifecycle, rate limiting,
claiming, reopening, max open tickets, close reason, initial description, stats.

Uses the ``temp_db`` fixture from conftest so each test gets an isolated database.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from services.ticket_service import (
    DEFAULT_MAX_OPEN_PER_USER,
    DEFAULT_REOPEN_WINDOW_HOURS,
    TICKET_RATE_LIMIT_SECONDS,
    TicketService,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def ticket_svc(temp_db: str) -> TicketService:
    """Provide an initialised TicketService backed by the temp database."""
    svc = TicketService()
    svc._initialized = True
    return svc


GUILD_ID = 100
USER_ID = 200
CHANNEL_ID = 300


# ---------------------------------------------------------------------------
# Category CRUD
# ---------------------------------------------------------------------------


class TestCategoryCRUD:
    """Tests for create / read / update / delete on ticket_categories."""

    @pytest.mark.asyncio
    async def test_create_category(self, ticket_svc: TicketService) -> None:
        """Creating a category returns a positive row ID."""
        cat_id = await ticket_svc.create_category(
            guild_id=GUILD_ID,
            name="General",
            description="General support",
            welcome_message="Hello!",
            role_ids=[1, 2],
            emoji="📩",
        )
        assert cat_id is not None
        assert cat_id > 0

    @pytest.mark.asyncio
    async def test_get_categories_empty(self, ticket_svc: TicketService) -> None:
        """No categories returns an empty list."""
        cats = await ticket_svc.get_categories(GUILD_ID)
        assert cats == []

    @pytest.mark.asyncio
    async def test_get_categories_ordered(self, ticket_svc: TicketService) -> None:
        """Categories are returned in sort_order."""
        await ticket_svc.create_category(GUILD_ID, "Alpha")
        await ticket_svc.create_category(GUILD_ID, "Beta")
        cats = await ticket_svc.get_categories(GUILD_ID)
        assert len(cats) == 2
        assert cats[0]["name"] == "Alpha"
        assert cats[1]["name"] == "Beta"

    @pytest.mark.asyncio
    async def test_get_category_by_id(self, ticket_svc: TicketService) -> None:
        """Retrieve a single category by its ID."""
        cat_id = await ticket_svc.create_category(GUILD_ID, "Bugs", emoji="🐛")
        cat = await ticket_svc.get_category(cat_id)  # type: ignore[arg-type]
        assert cat is not None
        assert cat["name"] == "Bugs"
        assert cat["emoji"] == "🐛"

    @pytest.mark.asyncio
    async def test_get_category_not_found(self, ticket_svc: TicketService) -> None:
        """Non-existent ID returns None."""
        assert await ticket_svc.get_category(99999) is None

    @pytest.mark.asyncio
    async def test_update_category(self, ticket_svc: TicketService) -> None:
        """Updating a category changes the stored values."""
        cat_id = await ticket_svc.create_category(GUILD_ID, "Old")
        assert cat_id is not None
        ok = await ticket_svc.update_category(cat_id, name="New", emoji="✨")
        assert ok is True
        cat = await ticket_svc.get_category(cat_id)
        assert cat is not None
        assert cat["name"] == "New"
        assert cat["emoji"] == "✨"

    @pytest.mark.asyncio
    async def test_update_category_not_found(self, ticket_svc: TicketService) -> None:
        """Updating a non-existent category returns False."""
        assert await ticket_svc.update_category(99999, name="X") is False

    @pytest.mark.asyncio
    async def test_update_category_role_ids(self, ticket_svc: TicketService) -> None:
        """Updating role_ids persists correctly as JSON."""
        cat_id = await ticket_svc.create_category(GUILD_ID, "Roles")
        assert cat_id is not None
        await ticket_svc.update_category(cat_id, role_ids=[10, 20])
        cat = await ticket_svc.get_category(cat_id)
        assert cat is not None
        assert cat["role_ids"] == [10, 20]

    @pytest.mark.asyncio
    async def test_update_no_valid_fields(self, ticket_svc: TicketService) -> None:
        """Passing unknown kwargs returns False without error."""
        cat_id = await ticket_svc.create_category(GUILD_ID, "No-op")
        assert cat_id is not None
        assert await ticket_svc.update_category(cat_id, unknown_field="x") is False

    @pytest.mark.asyncio
    async def test_delete_category(self, ticket_svc: TicketService) -> None:
        """Deleting a category removes it."""
        cat_id = await ticket_svc.create_category(GUILD_ID, "ToDelete")
        assert cat_id is not None
        assert await ticket_svc.delete_category(cat_id) is True
        assert await ticket_svc.get_category(cat_id) is None

    @pytest.mark.asyncio
    async def test_delete_category_not_found(self, ticket_svc: TicketService) -> None:
        """Deleting a non-existent category returns False."""
        assert await ticket_svc.delete_category(99999) is False


# ---------------------------------------------------------------------------
# Ticket Lifecycle
# ---------------------------------------------------------------------------


class TestTicketLifecycle:
    """Tests for creating, querying, and closing tickets."""

    @pytest.mark.asyncio
    async def test_create_ticket(self, ticket_svc: TicketService) -> None:
        """Creating a ticket returns a positive row ID."""
        tid = await ticket_svc.create_ticket(
            guild_id=GUILD_ID,
            channel_id=CHANNEL_ID,
            thread_id=1001,
            user_id=USER_ID,
        )
        assert tid is not None
        assert tid > 0

    @pytest.mark.asyncio
    async def test_get_ticket_by_thread(self, ticket_svc: TicketService) -> None:
        """Look up a ticket by its thread ID."""
        await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 2001, USER_ID)
        ticket = await ticket_svc.get_ticket_by_thread(2001)
        assert ticket is not None
        assert ticket["thread_id"] == 2001
        assert ticket["user_id"] == USER_ID
        assert ticket["status"] == "open"

    @pytest.mark.asyncio
    async def test_get_ticket_by_thread_not_found(self, ticket_svc: TicketService) -> None:
        """Non-existent thread ID returns None."""
        assert await ticket_svc.get_ticket_by_thread(99999) is None

    @pytest.mark.asyncio
    async def test_close_ticket(self, ticket_svc: TicketService) -> None:
        """Closing a ticket sets status to 'closed'."""
        tid = await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 3001, USER_ID)
        assert tid is not None
        closed = await ticket_svc.close_ticket(tid, closed_by=999)
        assert closed is True
        ticket = await ticket_svc.get_ticket_by_thread(3001)
        assert ticket is not None
        assert ticket["status"] == "closed"
        assert ticket["closed_by"] == 999
        assert ticket["closed_at"] is not None

    @pytest.mark.asyncio
    async def test_close_ticket_already_closed(self, ticket_svc: TicketService) -> None:
        """Closing an already-closed ticket returns False."""
        tid = await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 4001, USER_ID)
        assert tid is not None
        await ticket_svc.close_ticket(tid, closed_by=999)
        assert await ticket_svc.close_ticket(tid, closed_by=999) is False

    @pytest.mark.asyncio
    async def test_close_ticket_by_thread(self, ticket_svc: TicketService) -> None:
        """Close a ticket using the thread_id shortcut."""
        await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 5001, USER_ID)
        closed = await ticket_svc.close_ticket_by_thread(5001, closed_by=888)
        assert closed is True
        ticket = await ticket_svc.get_ticket_by_thread(5001)
        assert ticket is not None
        assert ticket["status"] == "closed"

    @pytest.mark.asyncio
    async def test_get_open_tickets(self, ticket_svc: TicketService) -> None:
        """get_open_tickets returns only open tickets."""
        await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 6001, USER_ID)
        await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 6002, USER_ID)
        tid3 = await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 6003, USER_ID)
        assert tid3 is not None
        await ticket_svc.close_ticket(tid3, closed_by=999)

        open_tickets = await ticket_svc.get_open_tickets(GUILD_ID)
        assert len(open_tickets) == 2

    @pytest.mark.asyncio
    async def test_get_open_tickets_by_user(self, ticket_svc: TicketService) -> None:
        """Filtering by user_id returns only that user's open tickets."""
        await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 7001, USER_ID)
        await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 7002, USER_ID + 1)

        user_tickets = await ticket_svc.get_open_tickets(GUILD_ID, user_id=USER_ID)
        assert len(user_tickets) == 1
        assert user_tickets[0]["user_id"] == USER_ID

    @pytest.mark.asyncio
    async def test_create_ticket_with_category(self, ticket_svc: TicketService) -> None:
        """Ticket with a category FK stores it correctly."""
        cat_id = await ticket_svc.create_category(GUILD_ID, "Support")
        tid = await ticket_svc.create_ticket(
            GUILD_ID, CHANNEL_ID, 8001, USER_ID, category_id=cat_id
        )
        assert tid is not None
        ticket = await ticket_svc.get_ticket_by_thread(8001)
        assert ticket is not None
        assert ticket["category_id"] == cat_id


# ---------------------------------------------------------------------------
# Pagination & Counts
# ---------------------------------------------------------------------------


class TestTicketQueries:
    """Tests for get_tickets, get_ticket_count, get_ticket_stats."""

    @pytest.mark.asyncio
    async def test_get_tickets_pagination(self, ticket_svc: TicketService) -> None:
        """Pagination returns the correct slice."""
        for i in range(5):
            await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 9000 + i, USER_ID)

        page1 = await ticket_svc.get_tickets(GUILD_ID, limit=2, offset=0)
        assert len(page1) == 2
        page2 = await ticket_svc.get_tickets(GUILD_ID, limit=2, offset=2)
        assert len(page2) == 2
        page3 = await ticket_svc.get_tickets(GUILD_ID, limit=2, offset=4)
        assert len(page3) == 1

    @pytest.mark.asyncio
    async def test_get_tickets_filter_status(self, ticket_svc: TicketService) -> None:
        """Filtering by status works."""
        await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 10001, USER_ID)
        tid2 = await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 10002, USER_ID)
        assert tid2 is not None
        await ticket_svc.close_ticket(tid2, closed_by=999)

        all_t = await ticket_svc.get_tickets(GUILD_ID)
        assert len(all_t) == 2
        open_t = await ticket_svc.get_tickets(GUILD_ID, status="open")
        assert len(open_t) == 1
        closed_t = await ticket_svc.get_tickets(GUILD_ID, status="closed")
        assert len(closed_t) == 1

    @pytest.mark.asyncio
    async def test_get_ticket_count(self, ticket_svc: TicketService) -> None:
        """Counting tickets by status."""
        await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 11001, USER_ID)
        tid2 = await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 11002, USER_ID)
        assert tid2 is not None
        await ticket_svc.close_ticket(tid2, closed_by=999)

        assert await ticket_svc.get_ticket_count(GUILD_ID) == 2
        assert await ticket_svc.get_ticket_count(GUILD_ID, status="open") == 1
        assert await ticket_svc.get_ticket_count(GUILD_ID, status="closed") == 1

    @pytest.mark.asyncio
    async def test_get_ticket_stats(self, ticket_svc: TicketService) -> None:
        """Stats return correct open/closed/total."""
        await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 12001, USER_ID)
        tid2 = await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 12002, USER_ID)
        assert tid2 is not None
        await ticket_svc.close_ticket(tid2, closed_by=999)

        stats = await ticket_svc.get_ticket_stats(GUILD_ID)
        assert stats["open"] == 1
        assert stats["closed"] == 1
        assert stats["total"] == 2


# ---------------------------------------------------------------------------
# Rate Limiting
# ---------------------------------------------------------------------------


class TestRateLimit:
    """Tests for the 5-minute per-user rate limit."""

    @pytest.mark.asyncio
    async def test_rate_limit_allows_first_ticket(self, ticket_svc: TicketService) -> None:
        """First ticket should always be allowed."""
        assert await ticket_svc.check_rate_limit(GUILD_ID, USER_ID) is True

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_after_recent_ticket(
        self, ticket_svc: TicketService
    ) -> None:
        """Second ticket within 5 minutes should be blocked."""
        await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 13001, USER_ID)
        assert await ticket_svc.check_rate_limit(GUILD_ID, USER_ID) is False

    @pytest.mark.asyncio
    async def test_cooldown_remaining_zero_when_no_ticket(
        self, ticket_svc: TicketService
    ) -> None:
        """No cooldown when user has no recent tickets."""
        assert await ticket_svc.get_cooldown_remaining(GUILD_ID, USER_ID) == 0

    @pytest.mark.asyncio
    async def test_cooldown_remaining_positive_after_ticket(
        self, ticket_svc: TicketService
    ) -> None:
        """Cooldown should be positive immediately after creating a ticket."""
        await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 14001, USER_ID)
        remaining = await ticket_svc.get_cooldown_remaining(GUILD_ID, USER_ID)
        assert 0 < remaining <= TICKET_RATE_LIMIT_SECONDS

    @pytest.mark.asyncio
    async def test_rate_limit_different_users(self, ticket_svc: TicketService) -> None:
        """Rate limit is per-user; different users are independent."""
        await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 15001, USER_ID)
        # Another user should be allowed
        assert await ticket_svc.check_rate_limit(GUILD_ID, USER_ID + 1) is True

    @pytest.mark.asyncio
    async def test_rate_limit_different_guilds(self, ticket_svc: TicketService) -> None:
        """Rate limit is per-guild; same user in a different guild is independent."""
        await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 16001, USER_ID)
        assert await ticket_svc.check_rate_limit(GUILD_ID + 1, USER_ID) is True

    @pytest.mark.asyncio
    async def test_reset_user_ticket_cooldown_allows_immediately(
        self, ticket_svc: TicketService
    ) -> None:
        """Per-user cooldown reset allows immediate ticket creation attempts."""
        await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 16002, USER_ID)
        assert await ticket_svc.check_rate_limit(GUILD_ID, USER_ID) is False

        reset_ok = await ticket_svc.reset_user_ticket_cooldown(GUILD_ID, USER_ID)
        assert reset_ok is True
        assert await ticket_svc.check_rate_limit(GUILD_ID, USER_ID) is True
        assert await ticket_svc.get_cooldown_remaining(GUILD_ID, USER_ID) == 0

    @pytest.mark.asyncio
    async def test_reset_all_ticket_cooldowns_allows_immediately(
        self, ticket_svc: TicketService
    ) -> None:
        """Guild-wide cooldown reset clears cooldown for users in that guild."""
        await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 16003, USER_ID)
        assert await ticket_svc.check_rate_limit(GUILD_ID, USER_ID) is False

        reset_ok = await ticket_svc.reset_all_ticket_cooldowns(GUILD_ID)
        assert reset_ok is True
        assert await ticket_svc.check_rate_limit(GUILD_ID, USER_ID) is True
        assert await ticket_svc.get_cooldown_remaining(GUILD_ID, USER_ID) == 0


# ---------------------------------------------------------------------------
# Close Reason
# ---------------------------------------------------------------------------


class TestCloseReason:
    """Tests for close_reason parameter on close operations."""

    @pytest.mark.asyncio
    async def test_close_ticket_with_reason(self, ticket_svc: TicketService) -> None:
        """Closing a ticket with a reason stores it."""
        tid = await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 17001, USER_ID)
        assert tid is not None
        closed = await ticket_svc.close_ticket(tid, closed_by=999, close_reason="Resolved")
        assert closed is True
        ticket = await ticket_svc.get_ticket_by_thread(17001)
        assert ticket is not None
        assert ticket["close_reason"] == "Resolved"

    @pytest.mark.asyncio
    async def test_close_ticket_by_thread_with_reason(self, ticket_svc: TicketService) -> None:
        """close_ticket_by_thread with reason stores it."""
        await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 17002, USER_ID)
        closed = await ticket_svc.close_ticket_by_thread(
            17002, closed_by=888, close_reason="Duplicate"
        )
        assert closed is True
        ticket = await ticket_svc.get_ticket_by_thread(17002)
        assert ticket is not None
        assert ticket["close_reason"] == "Duplicate"

    @pytest.mark.asyncio
    async def test_close_ticket_without_reason(self, ticket_svc: TicketService) -> None:
        """Closing without a reason stores None."""
        tid = await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 17003, USER_ID)
        assert tid is not None
        await ticket_svc.close_ticket(tid, closed_by=999)
        ticket = await ticket_svc.get_ticket_by_thread(17003)
        assert ticket is not None
        assert ticket["close_reason"] is None


# ---------------------------------------------------------------------------
# Initial Description
# ---------------------------------------------------------------------------


class TestInitialDescription:
    """Tests for initial_description on ticket creation."""

    @pytest.mark.asyncio
    async def test_create_ticket_with_description(self, ticket_svc: TicketService) -> None:
        """Ticket with initial description stores it."""
        tid = await ticket_svc.create_ticket(
            GUILD_ID, CHANNEL_ID, 18001, USER_ID,
            initial_description="I need help with X",
        )
        assert tid is not None
        ticket = await ticket_svc.get_ticket_by_thread(18001)
        assert ticket is not None
        assert ticket["initial_description"] == "I need help with X"

    @pytest.mark.asyncio
    async def test_create_ticket_without_description(self, ticket_svc: TicketService) -> None:
        """Ticket without description stores None."""
        tid = await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 18002, USER_ID)
        assert tid is not None
        ticket = await ticket_svc.get_ticket_by_thread(18002)
        assert ticket is not None
        assert ticket["initial_description"] is None


# ---------------------------------------------------------------------------
# Claim / Unclaim
# ---------------------------------------------------------------------------


class TestClaimTicket:
    """Tests for claiming and unclaiming tickets."""

    @pytest.mark.asyncio
    async def test_claim_ticket(self, ticket_svc: TicketService) -> None:
        """Claiming an open ticket sets claimed_by and claimed_at."""
        await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 19001, USER_ID)
        claimed = await ticket_svc.claim_ticket(19001, claimed_by=555)
        assert claimed is True
        ticket = await ticket_svc.get_ticket_by_thread(19001)
        assert ticket is not None
        assert ticket["claimed_by"] == 555
        assert ticket["claimed_at"] is not None

    @pytest.mark.asyncio
    async def test_claim_closed_ticket_fails(self, ticket_svc: TicketService) -> None:
        """Cannot claim a closed ticket."""
        tid = await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 19002, USER_ID)
        assert tid is not None
        await ticket_svc.close_ticket(tid, closed_by=999)
        claimed = await ticket_svc.claim_ticket(19002, claimed_by=555)
        assert claimed is False

    @pytest.mark.asyncio
    async def test_unclaim_ticket(self, ticket_svc: TicketService) -> None:
        """Unclaiming a ticket clears claimed_by and claimed_at."""
        await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 19003, USER_ID)
        await ticket_svc.claim_ticket(19003, claimed_by=555)
        unclaimed = await ticket_svc.unclaim_ticket(19003)
        assert unclaimed is True
        ticket = await ticket_svc.get_ticket_by_thread(19003)
        assert ticket is not None
        assert ticket["claimed_by"] is None
        assert ticket["claimed_at"] is None

    @pytest.mark.asyncio
    async def test_claim_nonexistent_ticket(self, ticket_svc: TicketService) -> None:
        """Claiming a non-existent thread returns False."""
        assert await ticket_svc.claim_ticket(99999, claimed_by=555) is False


# ---------------------------------------------------------------------------
# Reopen
# ---------------------------------------------------------------------------


class TestReopenTicket:
    """Tests for reopening closed tickets."""

    @pytest.mark.asyncio
    async def test_reopen_closed_ticket(self, ticket_svc: TicketService) -> None:
        """Reopening a closed ticket sets status back to open."""
        tid = await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 20001, USER_ID)
        assert tid is not None
        await ticket_svc.close_ticket(tid, closed_by=999)
        reopened = await ticket_svc.reopen_ticket(20001, reopened_by=USER_ID)
        assert reopened is True
        ticket = await ticket_svc.get_ticket_by_thread(20001)
        assert ticket is not None
        assert ticket["status"] == "open"
        assert ticket["reopened_by"] == USER_ID
        assert ticket["reopened_at"] is not None
        # Close fields should be cleared
        assert ticket["closed_by"] is None
        assert ticket["closed_at"] is None
        assert ticket["close_reason"] is None

    @pytest.mark.asyncio
    async def test_reopen_open_ticket_fails(self, ticket_svc: TicketService) -> None:
        """Cannot reopen an already-open ticket."""
        await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 20002, USER_ID)
        reopened = await ticket_svc.reopen_ticket(20002, reopened_by=USER_ID)
        assert reopened is False

    @pytest.mark.asyncio
    async def test_can_reopen_within_window(self, ticket_svc: TicketService) -> None:
        """can_reopen returns True for a recently closed ticket."""
        tid = await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 20003, USER_ID)
        assert tid is not None
        await ticket_svc.close_ticket(tid, closed_by=999)
        assert await ticket_svc.can_reopen(20003) is True

    @pytest.mark.asyncio
    async def test_can_reopen_outside_window(self, ticket_svc: TicketService) -> None:
        """can_reopen returns False if the ticket was closed long ago."""
        from services.db.repository import BaseRepository

        tid = await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 20004, USER_ID)
        assert tid is not None
        await ticket_svc.close_ticket(tid, closed_by=999)
        # Manually backdate closed_at
        old_time = int(time.time()) - (DEFAULT_REOPEN_WINDOW_HOURS * 3600 + 100)
        await BaseRepository.execute(
            "UPDATE tickets SET closed_at = ? WHERE thread_id = ?",
            (old_time, 20004),
        )
        assert await ticket_svc.can_reopen(20004) is False


# ---------------------------------------------------------------------------
# Max Open Tickets
# ---------------------------------------------------------------------------


class TestMaxOpenTickets:
    """Tests for max open ticket limit per user."""

    @pytest.mark.asyncio
    async def test_get_open_ticket_count(self, ticket_svc: TicketService) -> None:
        """Count only open tickets for a given user."""
        await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 21001, USER_ID)
        await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 21002, USER_ID)
        tid3 = await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 21003, USER_ID)
        assert tid3 is not None
        await ticket_svc.close_ticket(tid3, closed_by=999)

        count = await ticket_svc.get_open_ticket_count(GUILD_ID, USER_ID)
        assert count == 2

    @pytest.mark.asyncio
    async def test_check_max_open_tickets_under_limit(self, ticket_svc: TicketService) -> None:
        """User under the limit can open another ticket."""
        await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 22001, USER_ID)
        assert await ticket_svc.check_max_open_tickets(GUILD_ID, USER_ID, max_open=3) is True

    @pytest.mark.asyncio
    async def test_check_max_open_tickets_at_limit(self, ticket_svc: TicketService) -> None:
        """User at the limit cannot open another ticket."""
        await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 23001, USER_ID)
        await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 23002, USER_ID)
        assert await ticket_svc.check_max_open_tickets(GUILD_ID, USER_ID, max_open=2) is False

    @pytest.mark.asyncio
    async def test_check_max_open_tickets_default(self, ticket_svc: TicketService) -> None:
        """Default limit is DEFAULT_MAX_OPEN_PER_USER."""
        # Create DEFAULT_MAX_OPEN_PER_USER tickets
        for i in range(DEFAULT_MAX_OPEN_PER_USER):
            await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 24000 + i, USER_ID)
        assert await ticket_svc.check_max_open_tickets(GUILD_ID, USER_ID) is False


# ---------------------------------------------------------------------------
# Staff Role IDs (DRY helper)
# ---------------------------------------------------------------------------


class TestGetStaffRoleIds:
    """Tests for the static get_staff_role_ids helper."""

    @pytest.mark.asyncio
    async def test_parses_json_string(self) -> None:
        """Parses a JSON array string of role IDs."""
        config = AsyncMock()
        config.get_guild_setting.return_value = "[1, 2, 3]"
        result = await TicketService.get_staff_role_ids(config, GUILD_ID)
        assert result == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_handles_list_directly(self) -> None:
        """Handles when config returns a list directly."""
        config = AsyncMock()
        config.get_guild_setting.return_value = [10, 20]
        result = await TicketService.get_staff_role_ids(config, GUILD_ID)
        assert result == [10, 20]

    @pytest.mark.asyncio
    async def test_handles_empty(self) -> None:
        """Returns empty list when no roles configured."""
        config = AsyncMock()
        config.get_guild_setting.return_value = "[]"
        result = await TicketService.get_staff_role_ids(config, GUILD_ID)
        assert result == []

    @pytest.mark.asyncio
    async def test_handles_invalid_json(self) -> None:
        """Returns empty list on invalid JSON."""
        config = AsyncMock()
        config.get_guild_setting.return_value = "not_json"
        result = await TicketService.get_staff_role_ids(config, GUILD_ID)
        assert result == []

    @pytest.mark.asyncio
    async def test_handles_none(self) -> None:
        """Returns empty list when config returns None."""
        config = AsyncMock()
        config.get_guild_setting.return_value = None
        result = await TicketService.get_staff_role_ids(config, GUILD_ID)
        assert result == []


# ---------------------------------------------------------------------------
# Row converters
# ---------------------------------------------------------------------------


class TestRowConverters:
    """Tests for _row_to_ticket and _row_to_category static methods."""

    def test_row_to_ticket_full(self) -> None:
        """Full 16-column row is converted correctly."""
        row = (1, 100, 200, 300, 400, 5, "open", None, 1000, None, 555, 1001, "reason", "desc", 1002, 600)
        result = TicketService._row_to_ticket(row)
        assert result["id"] == 1
        assert result["claimed_by"] == 555
        assert result["close_reason"] == "reason"
        assert result["initial_description"] == "desc"
        assert result["reopened_at"] == 1002
        assert result["reopened_by"] == 600

    def test_row_to_ticket_legacy_10_columns(self) -> None:
        """Legacy 10-column row gracefully defaults new fields to None."""
        row = (1, 100, 200, 300, 400, 5, "open", None, 1000, None)
        result = TicketService._row_to_ticket(row)
        assert result["claimed_by"] is None
        assert result["close_reason"] is None
        assert result["initial_description"] is None

    def test_row_to_category(self) -> None:
        """Category row is converted correctly with JSON role_ids."""
        row = (1, 100, "Support", "Help", "Welcome!", "[1,2,3]", "📩", 0, 1000)
        result = TicketService._row_to_category(row)
        assert result["name"] == "Support"
        assert result["role_ids"] == [1, 2, 3]

    def test_row_to_category_empty_roles(self) -> None:
        """Category with empty/null role_ids returns empty list."""
        row = (1, 100, "Support", "Help", "Welcome!", "", None, 0, 1000)
        result = TicketService._row_to_category(row)
        assert result["role_ids"] == []


# ---------------------------------------------------------------------------
# get_ticket_by_id
# ---------------------------------------------------------------------------


class TestGetTicketById:
    """Tests for the single-row ticket lookup by primary key."""

    @pytest.mark.asyncio
    async def test_returns_ticket(self, ticket_svc: TicketService) -> None:
        """Retrieving a ticket by its ID returns the correct record."""
        tid = await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 50001, USER_ID)
        assert tid is not None
        ticket = await ticket_svc.get_ticket_by_id(tid)
        assert ticket is not None
        assert ticket["id"] == tid
        assert ticket["guild_id"] == GUILD_ID

    @pytest.mark.asyncio
    async def test_returns_none_not_found(self, ticket_svc: TicketService) -> None:
        """Non-existent ticket ID returns None."""
        result = await ticket_svc.get_ticket_by_id(99999)
        assert result is None

    @pytest.mark.asyncio
    async def test_scoped_by_guild(self, ticket_svc: TicketService) -> None:
        """Ticket lookup scoped to a different guild returns None."""
        tid = await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 50002, USER_ID)
        assert tid is not None

        # Same guild → found
        assert await ticket_svc.get_ticket_by_id(tid, guild_id=GUILD_ID) is not None

        # Different guild → not found
        assert await ticket_svc.get_ticket_by_id(tid, guild_id=999) is None

    @pytest.mark.asyncio
    async def test_no_guild_filter(self, ticket_svc: TicketService) -> None:
        """Without guild_id filter, ticket is returned regardless."""
        tid = await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 50003, USER_ID)
        assert tid is not None
        ticket = await ticket_svc.get_ticket_by_id(tid)
        assert ticket is not None
        assert ticket["id"] == tid
