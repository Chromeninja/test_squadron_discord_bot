"""Activity cadence helpers for metrics tier classification."""

from __future__ import annotations

from typing import Any

# Checked strictest-first; the first fully covered cadence wins.
TIER_CADENCE_DAYS: list[tuple[str, int]] = [
    ("hardcore", 1),
    ("regular", 3),
    ("casual", 7),
    ("reserve", 30),
]


def tier_from_cadence(
    active_days: set[int],
    range_start_day: int,
    range_days: int,
) -> str:
    """Derive activity tier from cadence-window coverage over a day range."""
    if not active_days:
        return "inactive"

    for tier_name, window_days in TIER_CADENCE_DAYS:
        if window_days > range_days:
            continue

        num_windows = -(-range_days // window_days)
        all_covered = True
        for index in range(num_windows):
            window_start = range_start_day + index * window_days
            window_end = range_start_day + min((index + 1) * window_days, range_days)
            if not any(window_start <= day < window_end for day in active_days):
                all_covered = False
                break

        if all_covered:
            return tier_name

    return "inactive"


def classify_member_activity_tiers(
    user_data: dict[int, dict[str, Any]],
    range_start_day: int,
    lookback_days: int,
) -> dict[int, dict[str, Any]]:
    """Build per-user tier payloads from intermediate day-bucket activity data."""
    result: dict[int, dict[str, Any]] = {}

    for user_id, data in user_data.items():
        active_chat_days = set(data.get("active_chat_days", set()))
        active_voice_days = set(data.get("active_voice_days", set()))
        active_game_days = set(data.get("active_game_days", set()))
        combined_days = active_chat_days | active_voice_days | active_game_days

        result[user_id] = {
            "last_chat_at": data.get("last_chat_at"),
            "last_voice_at": data.get("last_voice_at"),
            "last_game_at": data.get("last_game_at"),
            "voice_tier": tier_from_cadence(
                active_voice_days,
                range_start_day,
                lookback_days,
            ),
            "chat_tier": tier_from_cadence(
                active_chat_days,
                range_start_day,
                lookback_days,
            ),
            "game_tier": tier_from_cadence(
                active_game_days,
                range_start_day,
                lookback_days,
            ),
            "combined_tier": tier_from_cadence(
                combined_days,
                range_start_day,
                lookback_days,
            ),
        }

    return result
