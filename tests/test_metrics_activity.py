"""Characterization tests for metrics activity cadence helpers."""

from __future__ import annotations

from services.metrics_activity import classify_member_activity_tiers, tier_from_cadence


def test_tier_from_cadence_inactive_when_no_days() -> None:
    """No active days should classify as inactive."""
    # Arrange
    active_days: set[int] = set()

    # Act
    tier = tier_from_cadence(active_days, range_start_day=100, range_days=7)

    # Assert
    assert tier == "inactive"


def test_tier_from_cadence_hardcore_daily_coverage() -> None:
    """Daily coverage across range should classify as hardcore."""
    # Arrange
    active_days = {200, 201, 202, 203, 204, 205, 206}

    # Act
    tier = tier_from_cadence(active_days, range_start_day=200, range_days=7)

    # Assert
    assert tier == "hardcore"


def test_tier_from_cadence_regular_three_day_windows() -> None:
    """Coverage in each 3-day window should classify as regular."""
    # Arrange
    active_days = {300, 303, 306}

    # Act
    tier = tier_from_cadence(active_days, range_start_day=300, range_days=7)

    # Assert
    assert tier == "regular"


def test_tier_from_cadence_casual_weekly_window() -> None:
    """Single day in 7-day window should classify as casual."""
    # Arrange
    active_days = {405}

    # Act
    tier = tier_from_cadence(active_days, range_start_day=400, range_days=7)

    # Assert
    assert tier == "casual"


def test_tier_from_cadence_reserve_monthly_window() -> None:
    """One active day in 30-day range should classify as reserve."""
    # Arrange
    active_days = {529}  # last valid day in [500, 530) half-open range

    # Act
    tier = tier_from_cadence(active_days, range_start_day=500, range_days=30)

    # Assert
    assert tier == "reserve"


def test_classify_member_activity_tiers_combined_output_shape() -> None:
    """Classifier should return expected tier keys and preserve last timestamps."""
    # Arrange
    user_data = {
        123: {
            "active_chat_days": {10, 12},
            "active_voice_days": {10},
            "active_game_days": set(),
            "last_chat_at": 1715600100,
            "last_voice_at": 1715600200,
            "last_game_at": None,
        }
    }

    # Act
    result = classify_member_activity_tiers(
        user_data,
        range_start_day=10,
        lookback_days=7,
    )

    # Assert
    assert 123 in result
    assert result[123]["last_chat_at"] == 1715600100
    assert result[123]["last_voice_at"] == 1715600200
    assert "voice_tier" in result[123]
    assert "chat_tier" in result[123]
    assert "game_tier" in result[123]
    assert "combined_tier" in result[123]
