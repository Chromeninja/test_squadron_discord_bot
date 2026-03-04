"""Secure random utility helpers used for jitter and backoff calculations."""

from __future__ import annotations

import secrets


def secure_uniform(low: float, high: float) -> float:
    """Return a cryptographically strong pseudo-uniform float in [low, high)."""
    if high <= low:
        return low
    scale = 1_000_000
    fraction = secrets.randbelow(scale) / scale
    return low + ((high - low) * fraction)


def secure_randint(lower: int, upper: int) -> int:
    """Return a cryptographically strong integer in [lower, upper]."""
    if upper <= lower:
        return lower
    return lower + secrets.randbelow((upper - lower) + 1)
