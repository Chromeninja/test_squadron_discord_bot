"""Characterization tests for extracted database helper modules."""

from __future__ import annotations

from typing import Any

import pytest

from services.db.database import Database
from services.db.database import derive_membership_status as derive_from_database
from services.db.managed_event_mapper import managed_event_row_to_dict
from services.db.membership import derive_membership_status as derive_from_membership


def test_derive_membership_status_reexport_compatibility() -> None:
    """Ensure derive helper remains available from database module import path."""
    # Arrange
    main_orgs = ["TEST"]
    affiliate_orgs: list[str] = []

    # Act
    database_result = derive_from_database(main_orgs, affiliate_orgs, "TEST")
    membership_result = derive_from_membership(main_orgs, affiliate_orgs, "TEST")

    # Assert
    assert database_result == "main"
    assert membership_result == "main"


def test_managed_event_row_to_dict_maps_expected_fields() -> None:
    """Managed event mapper should return API payload with normalized values."""
    # Arrange
    row = {
        "id": 42,
        "name": "Event",
        "description": "Desc",
        "announcement_message": "Join us",
        "scheduled_start_time": "2026-05-13T12:00:00Z",
        "scheduled_end_time": "2026-05-13T13:00:00Z",
        "status": "scheduled",
        "entity_type": "voice",
        "channel_id": "123456",
        "location": None,
        "user_count_current": 7,
        "created_by_user_id": "111",
        "created_by_name": "Tester",
        "channel_name": "Event Coms",
        "image_url": "https://cdn.discordapp.com/guild-events/222/banner.png",
        "discord_event_id": "222",
        "announcement_message_id": "333",
        "signup_message_id": "444",
        "sync_status": "synced",
        "sync_error": None,
        "last_synced_at": 1715600000,
        "announcement_channel_id": "555",
        "revision": 3,
        "recurrence_rule": None,
        "recurrence_rule_payload": None,
    }

    # Act
    row_data: Any = row
    mapped = managed_event_row_to_dict(row_data)

    # Assert
    assert mapped["id"] == "42"
    assert mapped["user_count"] == 7
    assert mapped["channel_name"] == "Event Coms"
    assert mapped["image_url"] == "https://cdn.discordapp.com/guild-events/222/banner.png"
    assert mapped["source_of_truth"] == "db"


@pytest.mark.asyncio
async def test_upsert_managed_event_from_discord_preserves_display_metadata(
    temp_db: str,
) -> None:
    """Discord event imports should preserve UI display metadata."""
    # Arrange
    del temp_db
    recurrence_payload = {
        "start": "2026-06-02T20:00:00+00:00",
        "frequency": 2,
        "interval": 1,
        "by_weekday": [1],
    }
    discord_event_payload: dict[str, object | None] = {
        "id": "999888777666555444",
        "name": "Repeat Test",
        "description": "Weekly op",
        "scheduled_start_time": "2026-06-02T20:00:00+00:00",
        "scheduled_end_time": None,
        "status": "scheduled",
        "entity_type": "voice",
        "channel_id": "1182812153271558255",
        "channel_name": "Event Coms",
        "location": None,
        "user_count": 1,
        "image_url": "https://cdn.discordapp.com/guild-events/999888777666555444/banner.png",
        "recurrence_rule": "Weekly on Tuesday",
        "recurrence_rule_payload": recurrence_payload,
    }

    # Act
    imported_event = await Database.upsert_managed_event_from_discord(
        123,
        discord_event_payload,
    )

    # Assert
    assert imported_event["channel_name"] == "Event Coms"
    assert (
        imported_event["image_url"]
        == "https://cdn.discordapp.com/guild-events/999888777666555444/banner.png"
    )
    assert imported_event["recurrence_rule"] == "Weekly on Tuesday"
    assert imported_event["recurrence_rule_payload"] == recurrence_payload
