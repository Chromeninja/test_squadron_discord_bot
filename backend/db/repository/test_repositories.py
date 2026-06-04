"""Integration tests for backend repository classes against the real schema.

These tests exercise actual SQL against a temporary SQLite database
initialised from services/db/schema.py. They are the regression guard that
catches schema-mismatch bugs (wrong column names, missing NOT NULL fields)
that unit tests with mocked connections cannot detect.
"""

from __future__ import annotations

import pytest

from backend.db.repository.config import ConfigRepository
from backend.db.repository.tickets import TicketRepository
from backend.db.repository.verification import VerificationRepository
from backend.db.repository.voice import VoiceRepository

GUILD_ID = 555
USER_ID = 777


@pytest.mark.asyncio
async def test_ticket_create_get_update_close(temp_db: str) -> None:
    """Full ticket lifecycle against the real tickets schema."""
    repo = TicketRepository()

    created = await repo.create_ticket(
        GUILD_ID,
        {
            "channel_id": 1001,
            "thread_id": 2002,
            "user_id": USER_ID,
            "initial_description": "help please",
        },
    )
    ticket_id = int(created["id"])  # type: ignore[arg-type]
    assert created["status"] == "open"
    assert created["thread_id"] == 2002
    assert created["channel_id"] == 1001

    # Listing returns the open ticket
    open_tickets = await repo.get_tickets(GUILD_ID, status="open")
    assert any(t["id"] == ticket_id for t in open_tickets)

    # get_ticket round-trips
    fetched = await repo.get_ticket(GUILD_ID, ticket_id)
    assert fetched is not None
    assert fetched["user_id"] == USER_ID

    # update_ticket changes a whitelisted column
    updated = await repo.update_ticket(
        GUILD_ID, ticket_id, {"close_reason": "resolved"}
    )
    assert updated is not None
    assert updated["close_reason"] == "resolved"

    # close_ticket records closed_at/closed_by and flips status
    assert await repo.close_ticket(GUILD_ID, ticket_id, closed_by=999) is True
    closed = await repo.get_ticket(GUILD_ID, ticket_id)
    assert closed is not None
    assert closed["status"] == "closed"
    assert closed["closed_by"] == 999
    assert closed["closed_at"] is not None

    # Closing again is a no-op (already closed)
    assert await repo.close_ticket(GUILD_ID, ticket_id) is False


@pytest.mark.asyncio
async def test_ticket_create_requires_not_null_fields(temp_db: str) -> None:
    """Missing NOT NULL columns raise a clear error, not an SQLite crash."""
    repo = TicketRepository()
    with pytest.raises(ValueError, match="thread_id"):
        await repo.create_ticket(GUILD_ID, {"channel_id": 1, "user_id": 2})


@pytest.mark.asyncio
async def test_voice_channel_crud(temp_db: str) -> None:
    """Voice channel create/get/delete against the real voice_channels schema."""
    repo = VoiceRepository()
    created = await repo.create_voice_channel(
        GUILD_ID,
        {"voice_channel_id": 4004, "jtc_channel_id": 3003, "owner_id": USER_ID},
    )
    assert created is not None

    fetched = await repo.get_voice_channel(GUILD_ID, 4004)
    assert fetched is not None
    assert fetched["owner_id"] == USER_ID
    assert fetched["is_active"] == 1

    # get_jtc_channels only returns active channels
    active = await repo.get_jtc_channels(GUILD_ID)
    assert any(c["voice_channel_id"] == 4004 for c in active)

    # delete is a soft-delete (is_active -> 0); the row remains queryable
    assert await repo.delete_voice_channel(GUILD_ID, 4004) is True
    after = await repo.get_voice_channel(GUILD_ID, 4004)
    assert after is not None
    assert after["is_active"] == 0

    # ...and is excluded from the active listing
    active_after = await repo.get_jtc_channels(GUILD_ID)
    assert not any(c["voice_channel_id"] == 4004 for c in active_after)


@pytest.mark.asyncio
async def test_verification_create_and_fetch(temp_db: str) -> None:
    """Verification upsert and fetch against the real verification schema."""
    repo = VerificationRepository()
    await repo.create_verification(
        GUILD_ID,
        {
            "user_id": USER_ID,
            "rsi_handle": "TestPilot",
            "community_moniker": "Pilot",
            "main_orgs": "TEST",
            "affiliate_orgs": "",
        },
    )
    rec = await repo.get_verification(GUILD_ID, USER_ID)
    assert rec is not None
    assert rec["rsi_handle"] == "TestPilot"


@pytest.mark.asyncio
async def test_config_set_get_roundtrip(temp_db: str) -> None:
    """Config set/get roundtrip against the real guild_settings schema."""
    repo = ConfigRepository()

    # set_setting with a string value
    await repo.set_setting(GUILD_ID, "prefix", "!")
    result = await repo.get_setting(GUILD_ID, "prefix")
    assert result == "!"

    # set_setting with a dict value (JSON-encoded)
    dict_value = {"role_id": 12345, "enabled": True}
    await repo.set_setting(GUILD_ID, "moderation", dict_value)
    result = await repo.get_setting(GUILD_ID, "moderation")
    assert result == dict_value

    # get_config returns all settings for a guild
    await repo.set_setting(GUILD_ID, "timezone", "UTC")
    config = await repo.get_config(GUILD_ID)
    assert config["prefix"] == "!"
    assert config["moderation"] == dict_value
    assert config["timezone"] == "UTC"

    # get_setting on non-existent setting returns None
    result = await repo.get_setting(GUILD_ID, "nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_config_get_guild_roles(temp_db: str) -> None:
    """Test get_guild_roles with single and list role configs."""
    repo = ConfigRepository()

    # Set single role IDs (stored as list, extract first)
    await repo.set_setting(GUILD_ID, "roles.bot_verified_role", [123])
    await repo.set_setting(GUILD_ID, "roles.main_role", [456])
    await repo.set_setting(GUILD_ID, "roles.non_member_role", [789])

    # Set admin roles (stored as list)
    await repo.set_setting(GUILD_ID, "roles.bot_admins", [111, 222, 333])
    await repo.set_setting(GUILD_ID, "roles.event_coordinators", [444, 555])

    roles = await repo.get_guild_roles(GUILD_ID)
    assert roles["bot_verified_role_id"] == 123
    assert roles["main_role_id"] == 456
    assert roles["non_member_role_id"] == 789
    assert roles["bot_admin_role_ids"] == [111, 222, 333]
    assert roles["event_coordinator_role_ids"] == [444, 555]


@pytest.mark.asyncio
async def test_config_get_guild_channels(temp_db: str) -> None:
    """Test get_guild_channels with channel IDs."""
    repo = ConfigRepository()

    # Set channel IDs as integers
    await repo.set_setting(GUILD_ID, "channels.verification_channel_id", 1001)
    await repo.set_setting(GUILD_ID, "channels.bot_spam_channel_id", 1002)
    await repo.set_setting(GUILD_ID, "channels.public_announcement_channel_id", 1003)
    await repo.set_setting(
        GUILD_ID, "channels.leadership_announcement_channel_id", 1004
    )

    channels = await repo.get_guild_channels(GUILD_ID)
    assert channels["verification_channel_id"] == 1001
    assert channels["bot_spam_channel_id"] == 1002
    assert channels["public_announcement_channel_id"] == 1003
    assert channels["leadership_announcement_channel_id"] == 1004


@pytest.mark.asyncio
async def test_config_get_jtc_channels(temp_db: str) -> None:
    """Test get_jtc_channels with list of channel IDs."""
    repo = ConfigRepository()

    # Set JTC channels as list of integers
    jtc_list = [2001, 2002, 2003]
    await repo.set_setting(GUILD_ID, "voice.jtc_channels", jtc_list)

    channels = await repo.get_jtc_channels(GUILD_ID)
    assert channels == jtc_list
    assert isinstance(channels, list)
    assert all(isinstance(c, int) for c in channels)


@pytest.mark.asyncio
async def test_config_get_role_ids(temp_db: str) -> None:
    """Test get_role_ids generic method for list role configs."""
    repo = ConfigRepository()

    # Set a list of role IDs
    role_list = [100, 200, 300]
    await repo.set_setting(GUILD_ID, "roles.moderators", role_list)

    roles = await repo.get_role_ids(GUILD_ID, "roles.moderators")
    assert roles == role_list


@pytest.mark.asyncio
async def test_config_get_single_setting_int(temp_db: str) -> None:
    """Test get_single_setting_int for channel/role ID parsing."""
    repo = ConfigRepository()

    # Set a channel ID
    await repo.set_setting(GUILD_ID, "channels.verification_channel_id", 5001)

    channel_id = await repo.get_single_setting_int(
        GUILD_ID, "channels.verification_channel_id"
    )
    assert channel_id == 5001
    assert isinstance(channel_id, int)

    # Non-existent setting returns None
    result = await repo.get_single_setting_int(GUILD_ID, "nonexistent")
    assert result is None


# ------------------------------------------------------------------
# Ticket Category Tests
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ticket_category_create_get_update_delete(temp_db: str) -> None:
    """Full category lifecycle against the real ticket_categories schema."""
    repo = TicketRepository()

    # Create a category
    cat_id = await repo.create_category(
        GUILD_ID,
        name="Support",
        description="General support requests",
        welcome_message="Welcome to support!",
        role_ids=[100, 200],
        emoji="🎫",
        channel_id=1001,
    )
    assert cat_id is not None
    assert isinstance(cat_id, int)

    # Get the category
    category = await repo.get_category(cat_id)
    assert category is not None
    assert category["name"] == "Support"
    assert category["guild_id"] == GUILD_ID
    assert category["channel_id"] == 1001

    # List categories for guild
    categories = await repo.get_categories(GUILD_ID)
    assert any(c["id"] == cat_id for c in categories)

    # Update category
    updated = await repo.update_category(cat_id, name="Premium Support", emoji="✨")
    assert updated is True

    fetched = await repo.get_category(cat_id)
    assert fetched is not None
    assert fetched["name"] == "Premium Support"
    assert fetched["emoji"] == "✨"

    # Delete category
    deleted = await repo.delete_category(cat_id)
    assert deleted is True

    # Verify it's gone
    gone = await repo.get_category(cat_id)
    assert gone is None


@pytest.mark.asyncio
async def test_ticket_channel_ids(temp_db: str) -> None:
    """Test get_ticket_channel_ids returns distinct channels with categories."""
    repo = TicketRepository()

    # Create categories on channels 1001, 1002
    await repo.create_category(GUILD_ID, name="Cat1", channel_id=1001)
    await repo.create_category(GUILD_ID, name="Cat2", channel_id=1002)
    await repo.create_category(
        GUILD_ID, name="Cat3", channel_id=1001
    )  # Another on 1001

    channel_ids = await repo.get_ticket_channel_ids(GUILD_ID)
    assert 1001 in channel_ids
    assert 1002 in channel_ids
    assert len(set(channel_ids)) == len(channel_ids)  # No duplicates


# ------------------------------------------------------------------
# Channel Config Tests
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_channel_config_create_get_update_delete(temp_db: str) -> None:
    """Full channel config lifecycle against the real ticket_channel_configs schema."""
    repo = TicketRepository()

    # Create channel config
    config_id = await repo.create_channel_config(
        GUILD_ID,
        channel_id=1001,
        panel_title="Support Tickets",
        panel_description="Click to create a support ticket",
        panel_color="#0099ff",
        button_text="Create Ticket",
        button_emoji="🎫",
    )
    assert config_id is not None

    # Get the config
    config = await repo.get_channel_config(GUILD_ID, 1001)
    assert config is not None
    assert config["panel_title"] == "Support Tickets"
    assert config["button_emoji"] == "🎫"

    # List all configs for guild
    configs = await repo.get_channel_configs(GUILD_ID)
    assert any(c["id"] == config_id for c in configs)

    # Update config
    updated = await repo.update_channel_config(
        GUILD_ID,
        channel_id=1001,
        panel_title="Premium Support",
        enable_public_button=True,
    )
    assert updated is True

    fetched = await repo.get_channel_config(GUILD_ID, 1001)
    assert fetched is not None
    assert fetched["panel_title"] == "Premium Support"

    # Delete config
    deleted = await repo.delete_channel_config(GUILD_ID, 1001)
    assert deleted is True

    # Verify it's gone
    gone = await repo.get_channel_config(GUILD_ID, 1001)
    assert gone is None


# ------------------------------------------------------------------
# Ticket Query & Lifecycle Tests
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ticket_stats(temp_db: str) -> None:
    """Test get_ticket_stats returns correct counts."""
    repo = TicketRepository()

    # Create and track some tickets
    t1 = await repo.create_ticket(
        GUILD_ID,
        {
            "channel_id": 1001,
            "thread_id": 2001,
            "user_id": USER_ID,
        },
    )
    await repo.create_ticket(
        GUILD_ID,
        {
            "channel_id": 1001,
            "thread_id": 2002,
            "user_id": USER_ID,
        },
    )

    # Close one ticket
    ticket_id_1 = int(t1["id"])  # type: ignore[arg-type]
    await repo.close_ticket(GUILD_ID, ticket_id_1, closed_by=999)

    # Get stats
    stats = await repo.get_ticket_stats(GUILD_ID)
    assert stats["open"] == 1
    assert stats["closed"] == 1
    assert stats["total"] == 2


@pytest.mark.asyncio
async def test_ticket_claim_unclaim(temp_db: str) -> None:
    """Test claim and unclaim ticket by thread."""
    repo = TicketRepository()

    # Create a ticket
    await repo.create_ticket(
        GUILD_ID,
        {
            "channel_id": 1001,
            "thread_id": 2001,
            "user_id": USER_ID,
        },
    )

    # Claim it
    claimed = await repo.claim_ticket(2001, claimed_by=999)
    assert claimed is True

    # Verify claimed
    ticket = await repo.get_ticket_by_thread(2001)
    assert ticket is not None
    assert ticket["claimed_by"] == 999

    # Unclaim it
    unclaimed = await repo.unclaim_ticket(2001)
    assert unclaimed is True

    # Verify unclaimed
    ticket = await repo.get_ticket_by_thread(2001)
    assert ticket is not None
    assert ticket["claimed_by"] is None


@pytest.mark.asyncio
async def test_ticket_reopen_lifecycle(temp_db: str) -> None:
    """Test reopen ticket by thread."""
    repo = TicketRepository()

    # Create a ticket
    await repo.create_ticket(
        GUILD_ID,
        {
            "channel_id": 1001,
            "thread_id": 2001,
            "user_id": USER_ID,
        },
    )

    # Close it
    closed = await repo.close_ticket_by_thread(2001, closed_by=999)
    assert closed is True

    ticket = await repo.get_ticket_by_thread(2001)
    assert ticket is not None
    assert ticket["status"] == "closed"

    # Check if within reopen window (should be)
    can_reopen = await repo.can_reopen(2001)
    assert can_reopen is True

    # Reopen it
    reopened = await repo.reopen_ticket(2001, reopened_by=888)
    assert reopened is True

    # Verify reopened
    ticket = await repo.get_ticket_by_thread(2001)
    assert ticket is not None
    assert ticket["status"] == "open"
    assert ticket["reopened_by"] == 888


@pytest.mark.asyncio
async def test_mark_thread_deleted(temp_db: str) -> None:
    """Test marking a thread as deleted."""
    repo = TicketRepository()

    # Create a ticket
    await repo.create_ticket(
        GUILD_ID,
        {
            "channel_id": 1001,
            "thread_id": 2001,
            "user_id": USER_ID,
        },
    )

    # Mark as deleted
    marked = await repo.mark_thread_deleted(2001)
    assert marked is True

    # Verify deleted_at is set
    ticket = await repo.get_ticket_by_thread(2001)
    assert ticket is not None
    assert ticket["deleted_at"] is not None


@pytest.mark.asyncio
async def test_open_ticket_count(temp_db: str) -> None:
    """Test get_open_ticket_count for a user."""
    repo = TicketRepository()

    # Create multiple open tickets for a user
    await repo.create_ticket(
        GUILD_ID,
        {
            "channel_id": 1001,
            "thread_id": 2001,
            "user_id": USER_ID,
        },
    )
    await repo.create_ticket(
        GUILD_ID,
        {
            "channel_id": 1001,
            "thread_id": 2002,
            "user_id": USER_ID,
        },
    )

    # Create one for a different user
    await repo.create_ticket(
        GUILD_ID,
        {
            "channel_id": 1001,
            "thread_id": 2003,
            "user_id": 888,
        },
    )

    # Count for USER_ID
    count = await repo.get_open_ticket_count(GUILD_ID, USER_ID)
    assert count == 2

    # Count for other user
    other_count = await repo.get_open_ticket_count(GUILD_ID, 888)
    assert other_count == 1


# ------------------------------------------------------------------
# Ticket Form Integration Tests
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_form_step_create_get_update_delete(temp_db: str) -> None:
    """Full form step lifecycle against the real schema."""
    from backend.db.repository.ticket_forms import TicketFormRepository

    repo = TicketFormRepository()
    ticket_repo = TicketRepository()

    # Create a category first
    category_id = await ticket_repo.create_category(
        GUILD_ID,
        name="Test Category",
        description="Test",
        channel_id=9001,
    )
    assert category_id is not None

    # Create a step
    step_id = await repo.create_step(category_id, 1, "Step 1")
    assert step_id is not None

    # Get steps
    steps = await repo.get_steps(category_id)
    assert len(steps) == 1
    assert steps[0]["step_number"] == 1
    assert steps[0]["title"] == "Step 1"

    # Get single step
    step = await repo.get_step(category_id, 1)
    assert step is not None
    assert step["id"] == step_id

    # Update step
    updated = await repo.update_step(step_id, title="Updated Step 1")
    assert updated is True
    step = await repo.get_step(category_id, 1)
    assert step is not None
    assert step["title"] == "Updated Step 1"

    # Delete step
    deleted = await repo.delete_step(step_id)
    assert deleted is True
    steps = await repo.get_steps(category_id)
    assert len(steps) == 0


@pytest.mark.asyncio
async def test_form_question_create_get_update_delete(temp_db: str) -> None:
    """Full form question lifecycle."""
    from backend.db.repository.ticket_forms import TicketFormRepository

    repo = TicketFormRepository()
    ticket_repo = TicketRepository()

    # Create category and step
    category_id = await ticket_repo.create_category(
        GUILD_ID,
        name="Test Category",
        description="Test",
        channel_id=9001,
    )
    assert category_id is not None
    step_id = await repo.create_step(category_id, 1, "Step 1")
    assert step_id is not None

    # Create question
    qid = await repo.create_question(
        step_id,
        "q1",
        "Your Name",
        placeholder="Enter your name",
        style="short",
        required=True,
    )
    assert qid is not None

    # Get questions
    questions = await repo.get_questions(step_id)
    assert len(questions) == 1
    assert questions[0]["question_id"] == "q1"
    assert questions[0]["label"] == "Your Name"
    assert questions[0]["required"] is True

    # Update question
    updated = await repo.update_question(
        qid, label="Full Name", placeholder="Enter your full name"
    )
    assert updated is True
    questions = await repo.get_questions(step_id)
    assert questions[0]["label"] == "Full Name"
    assert questions[0]["placeholder"] == "Enter your full name"

    # Delete question
    deleted = await repo.delete_question(qid)
    assert deleted is True
    questions = await repo.get_questions(step_id)
    assert len(questions) == 0


@pytest.mark.asyncio
async def test_form_session_create_get_update_delete(temp_db: str) -> None:
    """Full session lifecycle."""
    from backend.db.repository.ticket_forms import TicketFormRepository

    repo = TicketFormRepository()
    ticket_repo = TicketRepository()

    # category_id has a FK to ticket_categories — create a real category first.
    category_id = await ticket_repo.create_category(
        GUILD_ID,
        name="Test Category",
        description="Test",
        channel_id=9001,
    )
    assert category_id is not None

    # Create session
    session = await repo.create_session(
        GUILD_ID,
        USER_ID,
        category_id,
        interaction_token="token123",  # noqa: S106
        is_public=True,
    )
    assert session is not None
    assert session["user_id"] == USER_ID
    assert session["category_id"] == category_id
    assert session["current_step"] == 1

    # Get session
    fetched = await repo.get_session(GUILD_ID, USER_ID)
    assert fetched is not None
    assert fetched["user_id"] == USER_ID

    # Update session
    answers = {"q1": {"answer": "John", "label": "Name", "step": 1}}
    updated = await repo.update_session(
        GUILD_ID,
        USER_ID,
        2,
        answers,
        interaction_token="token456",  # noqa: S106
    )
    assert updated is True
    fetched = await repo.get_session(GUILD_ID, USER_ID)
    assert fetched is not None
    assert fetched["current_step"] == 2

    # Delete session
    deleted = await repo.delete_session(GUILD_ID, USER_ID)
    assert deleted is True
    fetched = await repo.get_session(GUILD_ID, USER_ID)
    assert fetched is None


@pytest.mark.asyncio
async def test_form_get_form_config(temp_db: str) -> None:
    """Test getting full form config tree."""
    from backend.db.repository.ticket_forms import TicketFormRepository

    repo = TicketFormRepository()
    ticket_repo = TicketRepository()

    # Create category
    category_id = await ticket_repo.create_category(
        GUILD_ID,
        name="Test Category",
        description="Test",
        channel_id=9001,
    )
    assert category_id is not None

    # Create steps and questions
    step1_id = await repo.create_step(category_id, 1, "Step 1")
    assert step1_id is not None
    await repo.create_question(step1_id, "q1", "Name")
    await repo.create_question(step1_id, "q2", "Email", sort_order=1)

    step2_id = await repo.create_step(category_id, 2, "Step 2")
    assert step2_id is not None
    await repo.create_question(step2_id, "q3", "Message")

    # Get full config
    config = await repo.get_form_config(category_id)
    assert config is not None
    assert len(config["steps"]) == 2
    assert len(config["steps"][0]["questions"]) == 2
    assert len(config["steps"][1]["questions"]) == 1


@pytest.mark.asyncio
async def test_form_save_get_responses(temp_db: str) -> None:
    """Test saving and retrieving form responses."""
    from backend.db.repository.ticket_forms import TicketFormRepository

    repo = TicketFormRepository()
    ticket_repo = TicketRepository()

    # Create a ticket
    ticket = await ticket_repo.create_ticket(
        GUILD_ID,
        {
            "channel_id": 1001,
            "thread_id": 2001,
            "user_id": USER_ID,
        },
    )
    assert ticket is not None and ticket["id"] is not None
    ticket_id = int(ticket["id"])  # type: ignore[arg-type]

    # Save responses
    collected = {
        "q1": {"answer": "John Doe", "label": "Name", "step": 1, "sort_order": 0},
        "q2": {
            "answer": "john@example.com",
            "label": "Email",
            "step": 1,
            "sort_order": 1,
        },
    }
    saved = await repo.save_responses(ticket_id, collected)
    assert saved is True

    # Get responses
    responses = await repo.get_responses(ticket_id)
    assert len(responses) == 2
    assert responses[0]["question_id"] == "q1"
    assert responses[0]["answer"] == "John Doe"
    assert responses[1]["question_id"] == "q2"
    assert responses[1]["answer"] == "john@example.com"


# ------------------------------------------------------------------
# Ticket Category Extended Tests
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ticket_categories_for_channel(temp_db: str) -> None:
    """Test get_categories_for_channel returns only categories on specific channel."""
    repo = TicketRepository()

    # Create categories on different channels
    cat1 = await repo.create_category(GUILD_ID, name="Support", channel_id=1001)
    cat2 = await repo.create_category(GUILD_ID, name="Billing", channel_id=1002)
    cat3 = await repo.create_category(GUILD_ID, name="Other Support", channel_id=1001)

    # Get categories for channel 1001
    cats_1001 = await repo.get_categories_for_channel(GUILD_ID, 1001)
    assert len(cats_1001) == 2
    assert all(c["channel_id"] == 1001 for c in cats_1001)
    assert any(c["id"] == cat1 for c in cats_1001)
    assert any(c["id"] == cat3 for c in cats_1001)

    # Get categories for channel 1002
    cats_1002 = await repo.get_categories_for_channel(GUILD_ID, 1002)
    assert len(cats_1002) == 1
    assert cats_1002[0]["id"] == cat2


# ------------------------------------------------------------------
# Ticket Open Tickets Extended Tests
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_open_tickets_unfiltered(temp_db: str) -> None:
    """Test get_open_tickets returns all open tickets for a guild."""
    repo = TicketRepository()

    # Create multiple open tickets for different users
    await repo.create_ticket(
        GUILD_ID,
        {
            "channel_id": 1001,
            "thread_id": 2001,
            "user_id": USER_ID,
        },
    )
    await repo.create_ticket(
        GUILD_ID,
        {
            "channel_id": 1001,
            "thread_id": 2002,
            "user_id": 888,
        },
    )

    # Close one ticket
    await repo.close_ticket(GUILD_ID, 1, closed_by=999)

    # Get all open tickets
    open_tickets = await repo.get_open_tickets(GUILD_ID)
    assert len(open_tickets) == 1
    assert open_tickets[0]["user_id"] == 888


@pytest.mark.asyncio
async def test_get_open_tickets_filtered_by_user(temp_db: str) -> None:
    """Test get_open_tickets filtered by user_id."""
    repo = TicketRepository()

    # Create multiple tickets for the same user
    await repo.create_ticket(
        GUILD_ID,
        {
            "channel_id": 1001,
            "thread_id": 2001,
            "user_id": USER_ID,
        },
    )
    await repo.create_ticket(
        GUILD_ID,
        {
            "channel_id": 1001,
            "thread_id": 2002,
            "user_id": USER_ID,
        },
    )

    # Create one for a different user
    await repo.create_ticket(
        GUILD_ID,
        {
            "channel_id": 1001,
            "thread_id": 2003,
            "user_id": 888,
        },
    )

    # Get open tickets for USER_ID
    user_tickets = await repo.get_open_tickets(GUILD_ID, user_id=USER_ID)
    assert len(user_tickets) == 2
    assert all(t["user_id"] == USER_ID for t in user_tickets)


# ------------------------------------------------------------------
# VoiceRepository — command-path methods
# ------------------------------------------------------------------

JTC_ID = 9001
VC_ID = 9002


@pytest.mark.asyncio
async def test_voice_cooldown_check_and_update(temp_db: str) -> None:
    """check_cooldown returns False before an update and True after."""
    repo = VoiceRepository()

    # No cooldown set yet
    assert await repo.check_cooldown(GUILD_ID, JTC_ID, USER_ID, 60) is False

    # Set cooldown
    await repo.update_cooldown(GUILD_ID, JTC_ID, USER_ID)

    # Now on cooldown (60s window)
    assert await repo.check_cooldown(GUILD_ID, JTC_ID, USER_ID, 60) is True

    # Window of 0s → already expired
    assert await repo.check_cooldown(GUILD_ID, JTC_ID, USER_ID, 0) is False


@pytest.mark.asyncio
async def test_voice_user_channel_queries(temp_db: str) -> None:
    """get_user_channel_in_jtc, get_any_user_channel, get_user_channel_info."""
    repo = VoiceRepository()

    # Nothing exists yet
    assert await repo.get_user_channel_in_jtc(GUILD_ID, JTC_ID, USER_ID) is None
    assert await repo.get_any_user_channel(GUILD_ID, USER_ID) is None
    assert await repo.get_user_channel_info(GUILD_ID, USER_ID) is None

    # Insert a channel row
    await repo.create_voice_channel(
        GUILD_ID,
        {"jtc_channel_id": JTC_ID, "owner_id": USER_ID, "voice_channel_id": VC_ID},
    )

    assert await repo.get_user_channel_in_jtc(GUILD_ID, JTC_ID, USER_ID) == VC_ID
    assert await repo.get_any_user_channel(GUILD_ID, USER_ID) == VC_ID

    info = await repo.get_user_channel_info(GUILD_ID, USER_ID)
    assert info is not None
    assert info["voice_channel_id"] == VC_ID
    assert info["is_active"] is True


@pytest.mark.asyncio
async def test_voice_jtc_for_owned_channel(temp_db: str) -> None:
    """get_jtc_for_owned_channel returns jtc_channel_id for the owning user."""
    repo = VoiceRepository()

    await repo.create_voice_channel(
        GUILD_ID,
        {"jtc_channel_id": JTC_ID, "owner_id": USER_ID, "voice_channel_id": VC_ID},
    )

    assert await repo.get_jtc_for_owned_channel(GUILD_ID, VC_ID, USER_ID) == JTC_ID
    # Wrong owner → None
    assert await repo.get_jtc_for_owned_channel(GUILD_ID, VC_ID, 9999) is None


@pytest.mark.asyncio
async def test_voice_active_channels_list(temp_db: str) -> None:
    """get_all_active_channels and get_active_channel_ids return correct rows."""
    repo = VoiceRepository()

    await repo.create_voice_channel(
        GUILD_ID,
        {"jtc_channel_id": JTC_ID, "owner_id": USER_ID, "voice_channel_id": VC_ID},
    )
    await repo.create_voice_channel(
        GUILD_ID,
        {"jtc_channel_id": JTC_ID, "owner_id": 888, "voice_channel_id": 9003},
    )

    channels = await repo.get_all_active_channels(GUILD_ID)
    assert len(channels) == 2
    assert all("voice_channel_id" in c for c in channels)

    ids = await repo.get_active_channel_ids(GUILD_ID)
    assert set(ids) == {VC_ID, 9003}


@pytest.mark.asyncio
async def test_voice_cleanup_channel_records(temp_db: str) -> None:
    """cleanup_channel_records removes both channel and settings rows."""
    repo = VoiceRepository()

    await repo.create_voice_channel(
        GUILD_ID,
        {"jtc_channel_id": JTC_ID, "owner_id": USER_ID, "voice_channel_id": VC_ID},
    )

    # Confirm it exists
    assert await repo.get_voice_channel(GUILD_ID, VC_ID) is not None

    await repo.cleanup_channel_records(GUILD_ID, VC_ID)

    # Hard-deleted — row is gone
    assert await repo.get_voice_channel(GUILD_ID, VC_ID) is None


@pytest.mark.asyncio
async def test_voice_purge_voice_data(temp_db: str) -> None:
    """purge_voice_data deletes all voice rows for a guild."""
    repo = VoiceRepository()

    await repo.create_voice_channel(
        GUILD_ID,
        {"jtc_channel_id": JTC_ID, "owner_id": USER_ID, "voice_channel_id": VC_ID},
    )

    deleted = await repo.purge_voice_data(GUILD_ID)
    assert deleted["voice_channels"] >= 1

    # All gone
    assert await repo.get_active_channel_ids(GUILD_ID) == []


@pytest.mark.asyncio
async def test_voice_purge_stale_jtc_data(temp_db: str) -> None:
    """purge_stale_jtc_data deletes rows for stale JTC IDs only."""
    repo = VoiceRepository()

    await repo.create_voice_channel(
        GUILD_ID,
        {"jtc_channel_id": JTC_ID, "owner_id": USER_ID, "voice_channel_id": VC_ID},
    )
    await repo.create_voice_channel(
        GUILD_ID,
        {"jtc_channel_id": 9999, "owner_id": 888, "voice_channel_id": 9004},
    )

    # Only purge the stale JTC_ID
    deleted = await repo.purge_stale_jtc_data(GUILD_ID, {JTC_ID})
    assert deleted["voice_channels"] >= 1

    # VC_ID row gone; 9004 row survives
    remaining = await repo.get_active_channel_ids(GUILD_ID)
    assert 9004 in remaining


# ------------------------------------------------------------------
# Ticket Thread Health & Cleanup Tests
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ticket_thread_health(temp_db: str) -> None:
    """get_thread_health returns active/archived/deleted counts and status."""
    repo = TicketRepository()

    # Create 2 open tickets
    await repo.create_ticket(
        GUILD_ID,
        {
            "channel_id": 1001,
            "thread_id": 2001,
            "user_id": USER_ID,
            "initial_description": "ticket 1",
        },
    )
    await repo.create_ticket(
        GUILD_ID,
        {
            "channel_id": 1001,
            "thread_id": 2002,
            "user_id": USER_ID,
            "initial_description": "ticket 2",
        },
    )

    # Create and close 1 ticket
    closed = await repo.create_ticket(
        GUILD_ID,
        {
            "channel_id": 1001,
            "thread_id": 2003,
            "user_id": USER_ID,
            "initial_description": "ticket 3",
        },
    )
    closed_id = int(closed["id"])  # type: ignore[arg-type]
    await repo.close_ticket(GUILD_ID, closed_id, closed_by=999)

    # Get health stats
    health = await repo.get_thread_health(GUILD_ID, thread_limit=1000)
    assert health["active"] == 2
    assert health["archived"] == 1
    assert health["deleted"] == 0
    assert health["total_threads"] == 3
    assert health["limit"] == 1000
    assert health["status"] == "healthy"


@pytest.mark.asyncio
async def test_ticket_oldest_closed(temp_db: str) -> None:
    """get_oldest_closed_tickets returns closed tickets ordered by closed_at."""
    repo = TicketRepository()

    # Create and close a ticket
    ticket = await repo.create_ticket(
        GUILD_ID,
        {
            "channel_id": 1001,
            "thread_id": 3001,
            "user_id": USER_ID,
            "initial_description": "support request",
        },
    )
    ticket_id = int(ticket["id"])  # type: ignore[arg-type]
    await repo.close_ticket(GUILD_ID, ticket_id, closed_by=888)

    # Query oldest closed tickets
    oldest = await repo.get_oldest_closed_tickets(GUILD_ID, limit=5)
    assert len(oldest) >= 1
    assert any(t["id"] == ticket_id for t in oldest)


@pytest.mark.asyncio
async def test_ticket_cleanup_candidates(temp_db: str) -> None:
    """get_cleanup_candidates respects 30-day safety buffer (freshly closed tickets excluded)."""
    repo = TicketRepository()

    # Create and close a ticket (will have closed_at = now)
    ticket = await repo.create_ticket(
        GUILD_ID,
        {
            "channel_id": 1001,
            "thread_id": 4001,
            "user_id": USER_ID,
            "initial_description": "fresh ticket",
        },
    )
    ticket_id = int(ticket["id"])  # type: ignore[arg-type]
    await repo.close_ticket(GUILD_ID, ticket_id, closed_by=777)

    # Query cleanup candidates with 0 days (should enforce 30-day minimum)
    candidates = await repo.get_cleanup_candidates(GUILD_ID, older_than_days=0)
    # Freshly closed ticket should NOT appear (protected by 30-day buffer)
    assert not any(c["id"] == ticket_id for c in candidates)
