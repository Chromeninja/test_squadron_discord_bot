"""Characterization tests for extracted database helper modules."""

from __future__ import annotations

from typing import Any

from services.db.database import derive_membership_status as derive_from_database
from services.db.managed_event_mapper import (
    decode_signup_role_ids,
    managed_event_row_to_dict,
)
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


def test_decode_signup_role_ids_normalizes_values() -> None:
    """Decode helper should keep string/int IDs and drop unsupported types."""
    # Arrange
    raw_value = '["123", 456, null, true, "789"]'

    # Act
    decoded = decode_signup_role_ids(raw_value)

    # Assert
    assert decoded == ["123", "456", "789"]


def test_decode_signup_role_ids_invalid_payload_returns_empty_list() -> None:
    """Invalid JSON or non-list payloads should safely return an empty list."""
    # Arrange
    invalid_json = "{bad"
    invalid_type = '{"id": "123"}'

    # Act
    decoded_invalid_json = decode_signup_role_ids(invalid_json)
    decoded_invalid_type = decode_signup_role_ids(invalid_type)

    # Assert
    assert decoded_invalid_json == []
    assert decoded_invalid_type == []


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
        "discord_event_id": "222",
        "announcement_message_id": "333",
        "signup_message_id": "444",
        "sync_status": "synced",
        "sync_error": None,
        "last_synced_at": 1715600000,
        "announcement_channel_id": "555",
        "signup_role_ids": '["9", 10]',
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
    assert mapped["signup_role_ids"] == ["9", "10"]
    assert mapped["source_of_truth"] == "db"
