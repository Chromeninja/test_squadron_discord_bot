"""Shared helpers for parsing and normalizing Discord role ID lists."""

from __future__ import annotations

from typing import Any


def normalize_role_id_list(raw_role_ids: Any, *, strict: bool = False) -> list[int]:
    """Return normalized unique positive role IDs.

    Args:
        raw_role_ids: Input list-like role IDs (ints/strings).
        strict: When ``True``, raise ``ValueError`` on invalid list shape
            or invalid role IDs. When ``False``, invalid entries are ignored.

    Returns:
        Ordered unique positive integer role IDs.
    """
    if raw_role_ids is None:
        return []

    if not isinstance(raw_role_ids, list):
        if strict:
            raise ValueError("role IDs payload must be a list")
        return []

    normalized: list[int] = []
    for raw_role_id in raw_role_ids:
        try:
            role_id = int(raw_role_id)
        except (TypeError, ValueError) as exc:
            if strict:
                raise ValueError("role ID must be an integer") from exc
            continue

        if role_id <= 0:
            if strict:
                raise ValueError("role ID must be greater than zero")
            continue

        if role_id in normalized:
            continue
        normalized.append(role_id)

    return normalized
