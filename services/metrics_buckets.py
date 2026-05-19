"""Time bucket helpers for metrics aggregation windows."""

from __future__ import annotations


def hour_bucket(epoch: int) -> int:
    """Truncate a Unix timestamp to the start of its hour."""
    return epoch - (epoch % 3600)


def message_window_bucket(epoch: int) -> int:
    """Truncate a Unix timestamp to the start of its 3-minute message window."""
    return epoch - (epoch % 180)
