"""
Pagination constants and utilities for the web API.

Provides shared pagination defaults and caps for consistent behavior
across user and voice endpoints, especially for cross-guild queries
that may return large datasets (100k+ members).
"""

# --- Pagination Defaults ---

# Default page sizes
DEFAULT_PAGE_SIZE_USERS = 50
DEFAULT_PAGE_SIZE_VOICE = 50

# Maximum page sizes (caps)
MAX_PAGE_SIZE_USERS = 200
MAX_PAGE_SIZE_VOICE = 100

# Legacy maximum (for backward compatibility with existing search endpoints)
LEGACY_MAX_PAGE_SIZE = 100


def clamp_page_size(
    requested: int,
    default: int,
    maximum: int,
) -> int:
    """
    Clamp a requested page_size to valid bounds.

    Args:
        requested: The page_size requested by the client
        default: Default page size if requested is <= 0
        maximum: Maximum allowed page size

    Returns:
        Clamped page_size between 1 and maximum
    """
    if requested <= 0:
        return default
    return min(requested, maximum)


# Sentinel value for "All Guilds" mode (bot owner cross-guild view)
ALL_GUILDS_SENTINEL = "*"


def is_all_guilds_mode(active_guild_id: str | None) -> bool:
    """
    Check if the user is in "All Guilds" mode (bot owner cross-guild view).

    Args:
        active_guild_id: The user's active_guild_id from session

    Returns:
        True if in "All Guilds" mode
    """
    return active_guild_id == ALL_GUILDS_SENTINEL
