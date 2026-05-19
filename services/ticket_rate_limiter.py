"""Ticket rate limiting — cooldown checks and resets."""

from __future__ import annotations

import time

from services.db.repository import BaseRepository
from utils.logging import get_logger

logger = get_logger(__name__)

# Default rate-limit: one ticket per 5 minutes (300 seconds)
TICKET_RATE_LIMIT_SECONDS = 300

# Special user_id used for guild-wide cooldown reset markers.
_GLOBAL_COOLDOWN_RESET_USER_ID = 0


class TicketRateLimiter:
    """Rate limiting for ticket creation with per-user cooldowns."""

    def __init__(self) -> None:
        pass

    async def check_rate_limit(self, guild_id: int, user_id: int) -> bool:
        """Check whether the user can create a new ticket.

        Returns:
            ``True`` if the user is **allowed** (not rate-limited).
            ``False`` if they should wait.
        """
        cutoff = int(time.time()) - TICKET_RATE_LIMIT_SECONDS
        floor = await self._get_cooldown_floor(guild_id, user_id, cutoff)
        recent = await BaseRepository.exists(
            """
            SELECT 1 FROM tickets
            WHERE guild_id = ? AND user_id = ? AND created_at > ?
            """,
            (guild_id, user_id, floor),
        )
        return not recent

    async def get_cooldown_remaining(self, guild_id: int, user_id: int) -> int:
        """Return seconds remaining on the rate limit, or 0 if not limited."""
        cutoff = int(time.time()) - TICKET_RATE_LIMIT_SECONDS
        floor = await self._get_cooldown_floor(guild_id, user_id, cutoff)
        last_created: int | None = await BaseRepository.fetch_value(
            """
            SELECT MAX(created_at) FROM tickets
            WHERE guild_id = ? AND user_id = ? AND created_at > ?
            """,
            (guild_id, user_id, floor),
        )
        if last_created is None:
            return 0
        remaining = TICKET_RATE_LIMIT_SECONDS - (int(time.time()) - last_created)
        return max(remaining, 0)

    async def reset_user_ticket_cooldown(self, guild_id: int, user_id: int) -> bool:
        """Reset ticket cooldown timer for a specific user in a guild."""
        now = int(time.time())
        try:
            await self._ensure_cooldown_reset_table()
            await BaseRepository.execute(
                """
                INSERT INTO ticket_cooldown_resets (guild_id, user_id, reset_at)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, user_id)
                DO UPDATE SET reset_at = excluded.reset_at
                """,
                (guild_id, user_id, now),
            )
            return True
        except Exception as e:
            logger.exception(
                "Failed to reset ticket cooldown for user %s in guild %s",
                user_id,
                guild_id,
                exc_info=e,
            )
            return False

    async def reset_all_ticket_cooldowns(self, guild_id: int) -> bool:
        """Reset ticket cooldown timer for all users in a guild."""
        return await self.reset_user_ticket_cooldown(
            guild_id,
            _GLOBAL_COOLDOWN_RESET_USER_ID,
        )

    async def _ensure_cooldown_reset_table(self) -> None:
        """Ensure storage for cooldown reset markers exists."""
        await BaseRepository.execute(
            """
            CREATE TABLE IF NOT EXISTS ticket_cooldown_resets (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                reset_at INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )

    async def _get_cooldown_floor(
        self,
        guild_id: int,
        user_id: int,
        cutoff: int,
    ) -> int:
        """Return effective cutoff considering manual cooldown resets."""
        try:
            reset_at: int | None = await BaseRepository.fetch_value(
                """
                SELECT MAX(reset_at) FROM ticket_cooldown_resets
                WHERE guild_id = ? AND user_id IN (?, ?)
                """,
                (guild_id, _GLOBAL_COOLDOWN_RESET_USER_ID, user_id),
            )
        except Exception:
            return cutoff

        if reset_at is None:
            return cutoff
        return max(cutoff, int(reset_at))
