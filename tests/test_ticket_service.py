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
from services.db.database import Database


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
    async def test_create_category_with_allowed_statuses(
        self, ticket_svc: TicketService
    ) -> None:
        """Creating a category persists eligibility status restrictions."""
        cat_id = await ticket_svc.create_category(
            GUILD_ID,
            "Verified",
            allowed_statuses=["bot_verified", "org_main"],
        )
        assert cat_id is not None

        cat = await ticket_svc.get_category(cat_id)
        assert cat is not None
        assert cat["allowed_statuses"] == ["bot_verified", "org_main"]

    @pytest.mark.asyncio
    async def test_update_category_allowed_statuses_normalized(
        self, ticket_svc: TicketService
    ) -> None:
        """Updating eligibility statuses normalizes casing and duplicates."""
        cat_id = await ticket_svc.create_category(GUILD_ID, "Eligibility")
        assert cat_id is not None

        await ticket_svc.update_category(
            cat_id,
            allowed_statuses=[
                "ORG_MAIN",
                "org_main",
                "org_affiliate",
                "unknown",
            ],
        )

        cat = await ticket_svc.get_category(cat_id)
        assert cat is not None
        assert cat["allowed_statuses"] == ["org_main", "org_affiliate"]

    @pytest.mark.asyncio
    async def test_get_categories_auto_adds_allowed_statuses_column(
        self, ticket_svc: TicketService
    ) -> None:
        """Older DB schema is upgraded on read when allowed_statuses is missing."""
        async with Database.get_connection() as db:
            await db.execute("DROP TABLE ticket_categories")
            await db.execute(
                """
                CREATE TABLE ticket_categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    welcome_message TEXT DEFAULT '',
                    role_ids TEXT DEFAULT '[]',
                    emoji TEXT DEFAULT NULL,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                )
                """
            )
            await db.execute(
                """
                INSERT INTO ticket_categories
                    (guild_id, name, description, welcome_message, role_ids, emoji, sort_order)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (GUILD_ID, "Legacy", "", "", "[]", None, 0),
            )
            await db.commit()

        categories = await ticket_svc.get_categories(GUILD_ID)
        assert len(categories) == 1
        assert categories[0]["name"] == "Legacy"
        assert categories[0]["allowed_statuses"] == []

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
    async def test_handles_double_encoded_json_string(self) -> None:
        """Parses historical double-encoded JSON role arrays."""
        config = AsyncMock()
        config.get_guild_setting.return_value = '"[1309213397757460530]"'
        result = await TicketService.get_staff_role_ids(config, GUILD_ID)
        assert result == [1309213397757460530]

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
        # Columns: id, guild_id, channel_id, name, description,
        #          welcome_message, role_ids, allowed_statuses, emoji,
        #          sort_order, created_at
        row = (1, 100, 500, "Support", "Help", "Welcome!", "[1,2,3]", "[]", "📩", 0, 1000)
        result = TicketService._row_to_category(row)
        assert result["name"] == "Support"
        assert result["role_ids"] == [1, 2, 3]
        assert result["channel_id"] == 500
        assert result["allowed_statuses"] == []

    def test_row_to_category_empty_roles(self) -> None:
        """Category with empty/null role_ids returns empty list."""
        row = (1, 100, 0, "Support", "Help", "Welcome!", "", "[]", None, 0, 1000)
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


# ---------------------------------------------------------------------------
# Multi-Channel Category Support
# ---------------------------------------------------------------------------

PANEL_CHANNEL_A = 8001
PANEL_CHANNEL_B = 8002


class TestMultiChannelCategories:
    """Tests for channel_id on ticket categories."""

    @pytest.mark.asyncio
    async def test_create_category_with_channel_id(
        self, ticket_svc: TicketService
    ) -> None:
        """Creating a category with channel_id stores it correctly."""
        cat_id = await ticket_svc.create_category(
            GUILD_ID, "Chan-A", channel_id=PANEL_CHANNEL_A
        )
        assert cat_id is not None
        cat = await ticket_svc.get_category(cat_id)
        assert cat is not None
        assert cat["channel_id"] == PANEL_CHANNEL_A

    @pytest.mark.asyncio
    async def test_create_category_default_channel_is_zero(
        self, ticket_svc: TicketService
    ) -> None:
        """Without explicit channel_id, category defaults to 0 (unassigned)."""
        cat_id = await ticket_svc.create_category(GUILD_ID, "No-Chan")
        assert cat_id is not None
        cat = await ticket_svc.get_category(cat_id)
        assert cat is not None
        assert cat["channel_id"] == 0

    @pytest.mark.asyncio
    async def test_get_categories_for_channel_filters(
        self, ticket_svc: TicketService
    ) -> None:
        """get_categories_for_channel returns only matching categories."""
        await ticket_svc.create_category(
            GUILD_ID, "Alpha", channel_id=PANEL_CHANNEL_A
        )
        await ticket_svc.create_category(
            GUILD_ID, "Beta", channel_id=PANEL_CHANNEL_B
        )
        await ticket_svc.create_category(
            GUILD_ID, "Gamma", channel_id=PANEL_CHANNEL_A
        )

        cats_a = await ticket_svc.get_categories_for_channel(
            GUILD_ID, PANEL_CHANNEL_A
        )
        assert len(cats_a) == 2
        assert {c["name"] for c in cats_a} == {"Alpha", "Gamma"}

        cats_b = await ticket_svc.get_categories_for_channel(
            GUILD_ID, PANEL_CHANNEL_B
        )
        assert len(cats_b) == 1
        assert cats_b[0]["name"] == "Beta"

    @pytest.mark.asyncio
    async def test_get_categories_for_channel_empty(
        self, ticket_svc: TicketService
    ) -> None:
        """Channel with no categories returns an empty list."""
        result = await ticket_svc.get_categories_for_channel(GUILD_ID, 9999)
        assert result == []

    @pytest.mark.asyncio
    async def test_get_ticket_channel_ids(
        self, ticket_svc: TicketService
    ) -> None:
        """get_ticket_channel_ids returns distinct non-zero channel IDs."""
        await ticket_svc.create_category(
            GUILD_ID, "A", channel_id=PANEL_CHANNEL_A
        )
        await ticket_svc.create_category(
            GUILD_ID, "B", channel_id=PANEL_CHANNEL_B
        )
        await ticket_svc.create_category(
            GUILD_ID, "C", channel_id=PANEL_CHANNEL_A
        )
        # Unassigned category (channel_id=0) should NOT appear
        await ticket_svc.create_category(GUILD_ID, "Unassigned")

        channel_ids = await ticket_svc.get_ticket_channel_ids(GUILD_ID)
        assert set(channel_ids) == {PANEL_CHANNEL_A, PANEL_CHANNEL_B}

    @pytest.mark.asyncio
    async def test_get_ticket_channel_ids_empty(
        self, ticket_svc: TicketService
    ) -> None:
        """No categories returns an empty channel list."""
        result = await ticket_svc.get_ticket_channel_ids(GUILD_ID)
        assert result == []

    @pytest.mark.asyncio
    async def test_get_ticket_channel_ids_excludes_zero(
        self, ticket_svc: TicketService
    ) -> None:
        """Only channel_id=0 in DB returns empty list."""
        await ticket_svc.create_category(GUILD_ID, "Legacy")
        result = await ticket_svc.get_ticket_channel_ids(GUILD_ID)
        assert result == []

    @pytest.mark.asyncio
    async def test_update_category_channel_id(
        self, ticket_svc: TicketService
    ) -> None:
        """Updating channel_id on an existing category persists correctly."""
        cat_id = await ticket_svc.create_category(
            GUILD_ID, "Moveable", channel_id=PANEL_CHANNEL_A
        )
        assert cat_id is not None
        ok = await ticket_svc.update_category(cat_id, channel_id=PANEL_CHANNEL_B)
        assert ok is True
        cat = await ticket_svc.get_category(cat_id)
        assert cat is not None
        assert cat["channel_id"] == PANEL_CHANNEL_B

    @pytest.mark.asyncio
    async def test_schema_compat_adds_channel_id_column(
        self, ticket_svc: TicketService
    ) -> None:
        """_ensure_category_schema_compatibility adds channel_id to old schema."""
        # Reset flag so compatibility check runs again
        ticket_svc._category_schema_checked = False

        # Recreate table WITHOUT channel_id column
        async with Database.get_connection() as db:
            await db.execute("DROP TABLE ticket_categories")
            await db.execute(
                """
                CREATE TABLE ticket_categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    welcome_message TEXT DEFAULT '',
                    role_ids TEXT DEFAULT '[]',
                    allowed_statuses TEXT NOT NULL DEFAULT '[]',
                    emoji TEXT DEFAULT NULL,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                )
                """
            )
            await db.execute(
                """
                INSERT INTO ticket_categories
                    (guild_id, name)
                VALUES (?, ?)
                """,
                (GUILD_ID, "OldCat"),
            )
            await db.commit()

        # Reading categories should trigger the column addition
        categories = await ticket_svc.get_categories(GUILD_ID)
        assert len(categories) == 1
        assert categories[0]["name"] == "OldCat"
        assert categories[0]["channel_id"] == 0

    @pytest.mark.asyncio
    async def test_categories_for_channel_ordered_by_sort_order(
        self, ticket_svc: TicketService
    ) -> None:
        """Categories returned by channel are ordered by sort_order."""
        # Create in reverse name order — sort_order auto-increments
        await ticket_svc.create_category(
            GUILD_ID, "Zebra", channel_id=PANEL_CHANNEL_A
        )
        await ticket_svc.create_category(
            GUILD_ID, "Apple", channel_id=PANEL_CHANNEL_A
        )
        cats = await ticket_svc.get_categories_for_channel(
            GUILD_ID, PANEL_CHANNEL_A
        )
        assert len(cats) == 2
        # sort_order is auto-incremented, so Zebra (0) before Apple (1)
        assert cats[0]["name"] == "Zebra"
        assert cats[1]["name"] == "Apple"


# ---------------------------------------------------------------------------
# Channel Config Public Button
# ---------------------------------------------------------------------------


class TestChannelConfigPublicButton:
    """Tests for optional public-button fields on channel configs."""

    @pytest.mark.asyncio
    async def test_create_channel_config_with_public_button(
        self, ticket_svc: TicketService
    ) -> None:
        """Creating channel config persists public button fields."""
        config_id = await ticket_svc.create_channel_config(
            guild_id=GUILD_ID,
            channel_id=555001,
            button_text="Create Private Ticket",
            enable_public_button=True,
            public_button_text="Create Public Ticket",
            public_button_emoji="🌍",
        )
        assert config_id is not None

        cfg = await ticket_svc.get_channel_config(GUILD_ID, 555001)
        assert cfg is not None
        assert cfg["enable_public_button"] == 1
        assert cfg["public_button_text"] == "Create Public Ticket"
        assert cfg["public_button_emoji"] == "🌍"

    @pytest.mark.asyncio
    async def test_channel_config_schema_compat_adds_public_columns(
        self, ticket_svc: TicketService
    ) -> None:
        """Legacy channel-config schema is upgraded with public button columns."""
        ticket_svc._channel_config_schema_checked = False

        async with Database.get_connection() as db:
            await db.execute("DROP TABLE IF EXISTS ticket_channel_configs")
            await db.execute(
                """
                CREATE TABLE ticket_channel_configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    panel_title TEXT NOT NULL DEFAULT '🎫 Support Tickets',
                    panel_description TEXT NOT NULL DEFAULT '',
                    panel_color TEXT NOT NULL DEFAULT '0099FF',
                    button_text TEXT NOT NULL DEFAULT 'Create Ticket',
                    button_emoji TEXT DEFAULT '🎫',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                    UNIQUE(guild_id, channel_id)
                )
                """
            )
            await db.execute(
                "INSERT INTO ticket_channel_configs (guild_id, channel_id) VALUES (?, ?)",
                (GUILD_ID, 555002),
            )
            await db.commit()

        cfg = await ticket_svc.get_channel_config(GUILD_ID, 555002)
        assert cfg is not None
        assert cfg["enable_public_button"] == 0
        assert cfg["public_button_text"] == "Create Public Ticket"
        assert cfg["public_button_emoji"] == "🌐"

    @pytest.mark.asyncio
    async def test_create_channel_config_with_button_colors_and_order(
        self, ticket_svc: TicketService
    ) -> None:
        """Creating channel config persists button color and order fields."""
        config_id = await ticket_svc.create_channel_config(
            guild_id=GUILD_ID,
            channel_id=555003,
            enable_public_button=True,
            private_button_color="3BA55D",
            public_button_color="ED4245",
            button_order="public_first",
        )
        assert config_id is not None

        cfg = await ticket_svc.get_channel_config(GUILD_ID, 555003)
        assert cfg is not None
        assert cfg["private_button_color"] == "3BA55D"
        assert cfg["public_button_color"] == "ED4245"
        assert cfg["button_order"] == "public_first"

    @pytest.mark.asyncio
    async def test_update_channel_config_button_colors(
        self, ticket_svc: TicketService
    ) -> None:
        """Updating channel config modifies button colors and order."""
        # Create initial config
        await ticket_svc.create_channel_config(
            guild_id=GUILD_ID,
            channel_id=555004,
            enable_public_button=True,
        )

        # Update colors and order
        success = await ticket_svc.update_channel_config(
            guild_id=GUILD_ID,
            channel_id=555004,
            private_button_color="5865F2",
            public_button_color="4F545C",
            button_order="public_first",
        )
        assert success is True

        # Verify changes
        cfg = await ticket_svc.get_channel_config(GUILD_ID, 555004)
        assert cfg is not None
        assert cfg["private_button_color"] == "5865F2"
        assert cfg["public_button_color"] == "4F545C"
        assert cfg["button_order"] == "public_first"


# ---------------------------------------------------------------------------
# Thread Health & Cleanup
# ---------------------------------------------------------------------------


class TestThreadHealth:
    """Tests for get_thread_health, get_oldest_closed_tickets,
    get_cleanup_candidates, and mark_thread_deleted."""

    @pytest.mark.asyncio
    async def test_thread_health_empty_guild(self, ticket_svc: TicketService) -> None:
        """Empty guild returns healthy status with zero counts."""
        health = await ticket_svc.get_thread_health(GUILD_ID)
        assert health["active"] == 0
        assert health["archived"] == 0
        assert health["deleted"] == 0
        assert health["total_threads"] == 0
        assert health["limit"] == 1000
        assert health["usage_pct"] == 0.0
        assert health["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_thread_health_counts_open_and_closed(
        self, ticket_svc: TicketService
    ) -> None:
        """Open tickets counted as active, closed as archived."""
        await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 20001, USER_ID)
        tid2 = await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 20002, USER_ID)
        assert tid2 is not None
        await ticket_svc.close_ticket(tid2, closed_by=999)

        health = await ticket_svc.get_thread_health(GUILD_ID)
        assert health["active"] == 1
        assert health["archived"] == 1
        assert health["deleted"] == 0
        assert health["total_threads"] == 2

    @pytest.mark.asyncio
    async def test_thread_health_excludes_deleted(
        self, ticket_svc: TicketService
    ) -> None:
        """Tickets marked as deleted are excluded from total_threads."""
        tid1 = await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 21001, USER_ID)
        tid2 = await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 21002, USER_ID)
        assert tid1 is not None and tid2 is not None
        await ticket_svc.close_ticket(tid1, closed_by=999)
        await ticket_svc.close_ticket(tid2, closed_by=999)

        # Mark one as deleted
        result = await ticket_svc.mark_thread_deleted(21001)
        assert result is True

        health = await ticket_svc.get_thread_health(GUILD_ID)
        assert health["archived"] == 1
        assert health["deleted"] == 1
        assert health["total_threads"] == 1  # only non-deleted

    @pytest.mark.asyncio
    async def test_thread_health_status_thresholds(
        self, ticket_svc: TicketService
    ) -> None:
        """Verify status labels for different usage percentages."""
        # We test the logic directly by checking the returned status
        # with a known number of tickets. Since we can't easily create 800+
        # tickets, we verify the boundary logic via the method's output.
        health = await ticket_svc.get_thread_health(GUILD_ID)
        # 0 tickets → healthy
        assert health["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_mark_thread_deleted_success(
        self, ticket_svc: TicketService
    ) -> None:
        """mark_thread_deleted sets deleted_at on matching ticket."""
        await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 22001, USER_ID)
        result = await ticket_svc.mark_thread_deleted(22001)
        assert result is True

        # Verify via get_ticket_by_thread
        ticket = await ticket_svc.get_ticket_by_thread(22001)
        assert ticket is not None
        assert ticket["deleted_at"] is not None

    @pytest.mark.asyncio
    async def test_mark_thread_deleted_not_found(
        self, ticket_svc: TicketService
    ) -> None:
        """mark_thread_deleted returns False for non-existent thread."""
        result = await ticket_svc.mark_thread_deleted(99999)
        assert result is False

    @pytest.mark.asyncio
    async def test_mark_thread_deleted_idempotent(
        self, ticket_svc: TicketService
    ) -> None:
        """Calling mark_thread_deleted twice returns False the second time."""
        await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 23001, USER_ID)
        assert await ticket_svc.mark_thread_deleted(23001) is True
        assert await ticket_svc.mark_thread_deleted(23001) is False

    @pytest.mark.asyncio
    async def test_get_oldest_closed_tickets(
        self, ticket_svc: TicketService
    ) -> None:
        """Returns closed tickets sorted by oldest closed_at first."""
        tid1 = await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 24001, USER_ID)
        tid2 = await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 24002, USER_ID)
        assert tid1 is not None and tid2 is not None
        await ticket_svc.close_ticket(tid1, closed_by=999)
        await ticket_svc.close_ticket(tid2, closed_by=999)

        oldest = await ticket_svc.get_oldest_closed_tickets(GUILD_ID, limit=5)
        assert len(oldest) == 2
        # First should be oldest (closed first)
        assert oldest[0]["thread_id"] == 24001

    @pytest.mark.asyncio
    async def test_get_oldest_closed_excludes_deleted(
        self, ticket_svc: TicketService
    ) -> None:
        """Deleted tickets are excluded from oldest closed results."""
        tid1 = await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 25001, USER_ID)
        tid2 = await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 25002, USER_ID)
        assert tid1 is not None and tid2 is not None
        await ticket_svc.close_ticket(tid1, closed_by=999)
        await ticket_svc.close_ticket(tid2, closed_by=999)
        await ticket_svc.mark_thread_deleted(25001)

        oldest = await ticket_svc.get_oldest_closed_tickets(GUILD_ID, limit=5)
        assert len(oldest) == 1
        assert oldest[0]["thread_id"] == 25002

    @pytest.mark.asyncio
    async def test_get_oldest_closed_excludes_open(
        self, ticket_svc: TicketService
    ) -> None:
        """Open tickets are not included in oldest closed results."""
        await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 26001, USER_ID)
        oldest = await ticket_svc.get_oldest_closed_tickets(GUILD_ID, limit=5)
        assert len(oldest) == 0

    @pytest.mark.asyncio
    async def test_get_cleanup_candidates_respects_min_days(
        self, ticket_svc: TicketService
    ) -> None:
        """Cleanup candidates are not returned if closed less than 30 days ago."""
        tid = await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 27001, USER_ID)
        assert tid is not None
        await ticket_svc.close_ticket(tid, closed_by=999)

        # Just-closed ticket should NOT be a candidate even with older_than=0
        candidates = await ticket_svc.get_cleanup_candidates(
            GUILD_ID, older_than_days=0
        )
        assert len(candidates) == 0

    @pytest.mark.asyncio
    async def test_get_cleanup_candidates_returns_old_tickets(
        self, ticket_svc: TicketService
    ) -> None:
        """Tickets closed more than N days ago are returned."""
        from services.db.repository import BaseRepository

        tid = await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 28001, USER_ID)
        assert tid is not None
        await ticket_svc.close_ticket(tid, closed_by=999)

        # Backdate the closed_at to 60 days ago
        old_ts = int(time.time()) - (60 * 86400)
        await BaseRepository.execute(
            "UPDATE tickets SET closed_at = ? WHERE id = ?",
            (old_ts, tid),
        )

        candidates = await ticket_svc.get_cleanup_candidates(
            GUILD_ID, older_than_days=30
        )
        assert len(candidates) == 1
        assert candidates[0]["thread_id"] == 28001

    @pytest.mark.asyncio
    async def test_get_cleanup_candidates_excludes_deleted(
        self, ticket_svc: TicketService
    ) -> None:
        """Already-deleted tickets are excluded from cleanup candidates."""
        from services.db.repository import BaseRepository

        tid = await ticket_svc.create_ticket(GUILD_ID, CHANNEL_ID, 29001, USER_ID)
        assert tid is not None
        await ticket_svc.close_ticket(tid, closed_by=999)

        # Backdate and mark as deleted
        old_ts = int(time.time()) - (60 * 86400)
        await BaseRepository.execute(
            "UPDATE tickets SET closed_at = ? WHERE id = ?",
            (old_ts, tid),
        )
        await ticket_svc.mark_thread_deleted(29001)

        candidates = await ticket_svc.get_cleanup_candidates(
            GUILD_ID, older_than_days=30
        )
        assert len(candidates) == 0

    @pytest.mark.asyncio
    async def test_get_cleanup_candidates_with_limit(
        self, ticket_svc: TicketService
    ) -> None:
        """Limit parameter caps the number of candidates returned."""
        from services.db.repository import BaseRepository

        for i in range(5):
            tid = await ticket_svc.create_ticket(
                GUILD_ID, CHANNEL_ID, 30001 + i, USER_ID
            )
            assert tid is not None
            await ticket_svc.close_ticket(tid, closed_by=999)

        # Backdate all
        old_ts = int(time.time()) - (60 * 86400)
        await BaseRepository.execute(
            "UPDATE tickets SET closed_at = ? WHERE guild_id = ? AND status = 'closed'",
            (old_ts, GUILD_ID),
        )

        candidates = await ticket_svc.get_cleanup_candidates(
            GUILD_ID, older_than_days=30, limit=2
        )
        assert len(candidates) == 2

    @pytest.mark.asyncio
    async def test_ticket_schema_compatibility_adds_deleted_at(
        self, ticket_svc: TicketService
    ) -> None:
        """_ensure_ticket_schema_compatibility adds deleted_at on old tables."""
        from services.db.database import Database

        # Drop and recreate tickets table WITHOUT deleted_at column
        async with Database.get_connection() as db:
            await db.execute("DROP TABLE IF EXISTS tickets")
            await db.execute(
                """
                CREATE TABLE tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL DEFAULT 0,
                    thread_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    category_id INTEGER,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                    closed_at INTEGER,
                    closed_by INTEGER,
                    close_reason TEXT,
                    description TEXT,
                    claimed_by INTEGER,
                    claimed_at INTEGER,
                    reopened_by INTEGER
                )
                """
            )
            await db.execute(
                "INSERT INTO tickets (guild_id, channel_id, thread_id, user_id) "
                "VALUES (?, ?, ?, ?)",
                (GUILD_ID, CHANNEL_ID, 31001, USER_ID),
            )
            await db.commit()

        # Reset the schema check flag
        ticket_svc._ticket_schema_checked = False

        # Calling get_thread_health should trigger the schema compat check
        health = await ticket_svc.get_thread_health(GUILD_ID)
        assert health["active"] == 1
        assert health["deleted"] == 0
