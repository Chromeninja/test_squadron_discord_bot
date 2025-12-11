"""
Database Helper Module

Provides a centralized database interface for the Discord bot using aiosqlite.
Handles connection pooling and schema initialization.
"""

import asyncio
import json
import sqlite3
import time
from contextlib import asynccontextmanager

import aiosqlite

from utils.logging import get_logger

from .schema import init_schema

logger = get_logger(__name__)


def derive_membership_status(
    main_orgs: list[str] | None,
    affiliate_orgs: list[str] | None,
    target_sid: str = "TEST",
) -> str:
    """
    Derive membership status from organization SID lists.

    Checks if the target organization SID appears in the user's main or affiliate
    organization lists and returns the appropriate status.

    Args:
        main_orgs: List of main organization SIDs (typically 0 or 1 item)
        affiliate_orgs: List of affiliate organization SIDs
        target_sid: Organization SID to check for (defaults to "TEST")

    Returns:
        str: One of "main", "affiliate", or "non_member"
    """
    # Handle None or empty lists
    if not main_orgs:
        main_orgs = []
    if not affiliate_orgs:
        affiliate_orgs = []

    # Filter out REDACTED entries and check for target SID
    non_redacted_main = [sid for sid in main_orgs if sid != "REDACTED"]
    non_redacted_affiliate = [sid for sid in affiliate_orgs if sid != "REDACTED"]

    # Check main organizations first
    if target_sid in non_redacted_main:
        return "main"

    # Check affiliate organizations
    if target_sid in non_redacted_affiliate:
        return "affiliate"

    # Not a member of the target organization
    return "non_member"


async def get_cross_guild_membership_status(user_id: int) -> str:
    """
    Determine a user's highest membership status across ALL guilds tracking their orgs.

    Returns the highest status ("main", "affiliate", or "non_member") by:
    1. Fetching user's main_orgs and affiliate_orgs from verification table
    2. Finding all guilds that track ANY of those organizations
    3. Returning "main" if user is main member of ANY tracked org
    4. Returning "affiliate" if only affiliate across all tracked orgs
    5. Returning "non_member" if not a member of any tracked org

    This is used for auto-recheck cadence: 14 days for main, 7 for affiliate, 3 for non-member.

    Args:
        user_id: Discord user ID

    Returns:
        str: "main", "affiliate", or "non_member"
    """
    async with Database.get_connection() as db:
        # Get user's organization memberships
        cur = await db.execute(
            "SELECT main_orgs, affiliate_orgs FROM verification WHERE user_id = ?",
            (user_id,),
        )
        row = await cur.fetchone()

        if not row:
            return "non_member"

        main_orgs_json, affiliate_orgs_json = row
        main_orgs = json.loads(main_orgs_json) if main_orgs_json else []
        affiliate_orgs = json.loads(affiliate_orgs_json) if affiliate_orgs_json else []

        # Filter out REDACTED
        main_orgs = [sid for sid in main_orgs if sid != "REDACTED"]
        affiliate_orgs = [sid for sid in affiliate_orgs if sid != "REDACTED"]

        if not main_orgs and not affiliate_orgs:
            return "non_member"

        # Get all tracked organization SIDs from guild_settings
        # We need to find guilds where organization.sid matches any of user's orgs
        all_user_orgs = set(main_orgs + affiliate_orgs)

        # Query guild_settings for any guild tracking these orgs
        tracked_orgs_query = """
            SELECT json_extract(value, '$') as org_sid
            FROM guild_settings
            WHERE key = 'organization.sid'
            AND json_extract(value, '$') IS NOT NULL
        """
        cur = await db.execute(tracked_orgs_query)
        tracked_sids_rows = await cur.fetchall()
        tracked_sids = {
            row[0].strip('"').upper() for row in tracked_sids_rows if row[0]
        }

        # Check intersection
        tracked_user_orgs = all_user_orgs.intersection(tracked_sids)

        if not tracked_user_orgs:
            return "non_member"

        # Determine highest status
        for org_sid in tracked_user_orgs:
            if org_sid in main_orgs:
                return "main"  # Highest status

        # If we get here, user is only affiliate in tracked orgs
        return "affiliate"


class Database:
    _db_path: str = "TESTDatabase.db"
    _lock = asyncio.Lock()  # Ensures that only one initialization happens
    _initialized = False

    @classmethod
    async def get_auto_recheck_fail_count(cls, user_id: int) -> int:
        """
        Return the current fail_count for a user in auto_recheck_state, or 0 if no row.
        """
        async with cls.get_connection() as db:
            cur = await db.execute(
                "SELECT fail_count FROM auto_recheck_state WHERE user_id = ?",
                (user_id,),
            )
            row = await cur.fetchone()
            return int(row[0]) if row and row[0] is not None else 0

    @classmethod
    async def initialize(cls, db_path: str | None = None) -> None:
        async with cls._lock:
            if cls._initialized:
                return
            if db_path:
                cls._db_path = db_path
                # No need to keep the connection open after initialization
            async with aiosqlite.connect(cls._db_path) as db:
                # Enable foreign key constraints
                await db.execute("PRAGMA foreign_keys=ON")
                # Initialize schema using the centralized schema module
                await init_schema(db)
            cls._initialized = True
            logger.info("Database initialized.")

    @classmethod
    async def ensure_verification_row(cls, user_id: int) -> None:
        """
        Ensure a verification row exists for the user before any rate_limits operations.

        Prevents sqlite3.IntegrityError: FOREIGN KEY constraint failed by creating
        a minimal placeholder verification row if none exists.

        Args:
            user_id: Discord user ID to ensure has a verification row
        """
        async with cls.get_connection() as db:
            # INSERT OR IGNORE ensures idempotent behavior - no clobbering of existing rows
            await db.execute(
                """
                INSERT OR IGNORE INTO verification(user_id, rsi_handle, last_updated, verification_payload, needs_reverify, needs_reverify_at, community_moniker)
                VALUES (?, '', 0, NULL, 0, 0, NULL)
            """,
                (user_id,),
            )
            await db.commit()

    @classmethod
    @classmethod
    @asynccontextmanager
    async def get_connection(cls):
        """
        Get a connection to the database with optimized settings.

        Usage:
            async with Database.get_connection() as db:
                await db.execute("SELECT * FROM table")
        """
        if not cls._initialized:
            await cls.initialize()
        async with aiosqlite.connect(cls._db_path) as db:
            # Optimize database performance and reliability
            await db.execute("PRAGMA busy_timeout=5000")
            await db.execute("PRAGMA foreign_keys=ON")
            try:
                await db.execute("PRAGMA journal_mode=WAL")
            except sqlite3.OperationalError as exc:
                # WAL transition can fail briefly if another writer holds a lock; retry once
                if "database is locked" in str(exc).lower():
                    await asyncio.sleep(0.05)
                    await db.execute("PRAGMA journal_mode=WAL")
                else:
                    raise
            await db.execute("PRAGMA synchronous=NORMAL")
            db.row_factory = aiosqlite.Row
            yield db

    @classmethod
    async def fetch_rate_limit(
        cls, user_id: int, action: str
    ) -> tuple[int, int] | None:
        """Fetch rate limit counters for a user/action pair."""
        async with cls.get_connection() as db:
            cursor = await db.execute(
                "SELECT attempt_count, first_attempt FROM rate_limits WHERE user_id = ? AND action = ?",
                (user_id, action),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            # aiosqlite.Row supports both index and key access
            return int(row[0]), int(row[1])

    @classmethod
    async def has_reported_missing_roles(cls, guild_id: int) -> bool:
        """Return True if we've previously recorded a missing-role warning for this guild."""
        async with cls.get_connection() as db:
            cursor = await db.execute(
                "SELECT 1 FROM missing_role_warnings WHERE guild_id = ?", (guild_id,)
            )
            return (await cursor.fetchone()) is not None

    @classmethod
    async def mark_reported_missing_roles(cls, guild_id: int) -> None:
        """Record that we've warned about missing configured roles for this guild."""
        now = int(time.time())
        async with cls.get_connection() as db:
            await db.execute(
                "INSERT OR IGNORE INTO missing_role_warnings (guild_id, reported_at) VALUES (?, ?)",
                (guild_id, now),
            )
            await db.commit()

    @classmethod
    async def increment_rate_limit(cls, user_id: int, action: str) -> None:
        # Ensure verification row exists before touching rate_limits (prevent FK errors)
        await cls.ensure_verification_row(user_id)

        now = int(time.time())
        async with cls.get_connection() as db:
            await db.execute(
                """
                INSERT INTO rate_limits(user_id, action, attempt_count, first_attempt)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(user_id, action) DO UPDATE SET attempt_count=attempt_count+1
                """,
                (user_id, action, now),
            )
            await db.commit()

    @classmethod
    async def check_and_increment_rate_limit(
        cls, user_id: int, action: str, max_attempts: int, window: int
    ) -> tuple[bool, int]:
        """
        Atomically check and increment rate limit in a single transaction.

        This prevents race conditions where concurrent requests could bypass limits.

        Args:
            user_id: Discord user ID
            action: Rate limit action type ("verification" or "recheck")
            max_attempts: Maximum allowed attempts in window
            window: Time window in seconds

        Returns:
            Tuple of (is_rate_limited, wait_until_timestamp)
            - is_rate_limited: True if user has exceeded rate limit
            - wait_until_timestamp: Unix timestamp when rate limit expires (0 if not limited)
        """
        # Ensure verification row exists before touching rate_limits (prevent FK errors)
        await cls.ensure_verification_row(user_id)

        now = int(time.time())

        async with cls.get_connection() as db:
            # Use BEGIN IMMEDIATE to acquire write lock immediately
            await db.execute("BEGIN IMMEDIATE")
            try:
                cursor = await db.execute(
                    "SELECT attempt_count, first_attempt FROM rate_limits WHERE user_id = ? AND action = ?",
                    (user_id, action),
                )
                row = await cursor.fetchone()

                if row:
                    attempts, first = row
                    if now - first >= window:
                        # Window expired - reset to 1 attempt
                        await db.execute(
                            "UPDATE rate_limits SET attempt_count = 1, first_attempt = ? WHERE user_id = ? AND action = ?",
                            (now, user_id, action),
                        )
                        await db.commit()
                        return False, 0
                    elif attempts >= max_attempts:
                        # Already at limit
                        await db.commit()
                        return True, first + window
                    else:
                        # Increment counter
                        await db.execute(
                            "UPDATE rate_limits SET attempt_count = attempt_count + 1 WHERE user_id = ? AND action = ?",
                            (user_id, action),
                        )
                        await db.commit()
                        return False, 0
                else:
                    # First attempt
                    await db.execute(
                        "INSERT INTO rate_limits (user_id, action, attempt_count, first_attempt) VALUES (?, ?, 1, ?)",
                        (user_id, action, now),
                    )
                    await db.commit()
                    return False, 0
            except Exception:
                await db.rollback()
                raise

    @classmethod
    async def reset_rate_limit(
        cls, user_id: int | None = None, action: str | None = None
    ) -> None:
        async with cls.get_connection() as db:
            if user_id is None:
                await db.execute("DELETE FROM rate_limits")
            elif action is None:
                await db.execute(
                    "DELETE FROM rate_limits WHERE user_id = ?", (user_id,)
                )
            else:
                await db.execute(
                    "DELETE FROM rate_limits WHERE user_id = ? AND action = ?",
                    (user_id, action),
                )
            await db.commit()

    @classmethod
    async def upsert_auto_recheck_success(
        cls, user_id: int, next_retry_at: int, now: int, new_fail_count: int = 0
    ) -> None:
        async with cls.get_connection() as db:
            await db.execute(
                """
                INSERT INTO auto_recheck_state(user_id, last_auto_recheck, next_retry_at, fail_count, last_error)
                VALUES (?, ?, ?, ?, NULL)
                ON CONFLICT(user_id) DO UPDATE SET
                    last_auto_recheck=excluded.last_auto_recheck,
                    next_retry_at=excluded.next_retry_at,
                    fail_count=excluded.fail_count,
                    last_error=NULL
            """,
                (user_id, now, next_retry_at, new_fail_count),
            )
            await db.commit()

    @classmethod
    async def upsert_auto_recheck_failure(
        cls,
        user_id: int,
        next_retry_at: int,
        now: int,
        error_msg: str,
        inc: bool = True,
    ) -> None:
        async with cls.get_connection() as db:
            if inc:
                await db.execute(
                    """
                    INSERT INTO auto_recheck_state(user_id, last_auto_recheck, next_retry_at, fail_count, last_error)
                    VALUES (?, ?, ?, 1, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        last_auto_recheck=excluded.last_auto_recheck,
                        next_retry_at=excluded.next_retry_at,
                        fail_count=fail_count+1,
                        last_error=excluded.last_error
                """,
                    (user_id, now, next_retry_at, error_msg[:500]),
                )
            else:
                await db.execute(
                    """
                    INSERT INTO auto_recheck_state(user_id, last_auto_recheck, next_retry_at, fail_count, last_error)
                    VALUES (?, ?, ?, 0, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        last_auto_recheck=excluded.last_auto_recheck,
                        next_retry_at=excluded.next_retry_at,
                        last_error=excluded.last_error
                """,
                    (user_id, now, next_retry_at, error_msg[:500]),
                )
            await db.commit()

    @classmethod
    async def get_due_auto_rechecks(cls, now: int, limit: int) -> list[tuple[int, str]]:
        """
        Returns list of (user_id, rsi_handle) that are due for auto recheck.
        If a user has no row in auto_recheck_state, treat as due (bootstrap on first touch).
        """
        async with cls.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT v.user_id, v.rsi_handle
                FROM verification v
                LEFT JOIN auto_recheck_state s ON s.user_id = v.user_id
                WHERE COALESCE(s.next_retry_at, 0) <= ?
                  AND v.needs_reverify = 0
                ORDER BY COALESCE(s.last_auto_recheck, 0) ASC
                LIMIT ?
            """,
                (now, limit),
            )
            rows = await cursor.fetchall()
            # Normalize to a list of simple tuples for typing clarity
            return [(int(r[0]), str(r[1])) for r in rows]

    # 404 handle change helpers (older 'username_404' module name retained for backward compatibility)
    @classmethod
    async def flag_needs_reverify(cls, user_id: int, now: int) -> bool:
        """Set needs_reverify flag. Returns True if row updated (was newly flagged)."""
        async with cls.get_connection() as db:
            cur = await db.execute(
                "UPDATE verification SET needs_reverify=1, needs_reverify_at=? WHERE user_id=? AND needs_reverify=0",
                (now, user_id),
            )
            await db.commit()
            return cur.rowcount > 0

    @classmethod
    async def clear_needs_reverify(cls, user_id: int) -> None:
        async with cls.get_connection() as db:
            await db.execute(
                "UPDATE verification SET needs_reverify=0, needs_reverify_at=NULL WHERE user_id=?",
                (user_id,),
            )
            await db.commit()

    @classmethod
    async def unschedule_auto_recheck(cls, user_id: int) -> None:
        """Remove any auto-recheck state for a user (stop further auto checks)."""
        async with cls.get_connection() as db:
            await db.execute(
                "DELETE FROM auto_recheck_state WHERE user_id = ?", (user_id,)
            )
            await db.commit()

    @classmethod
    async def get_user_active_guilds(cls, user_id: int) -> list[int]:
        """Return guild IDs where the user is currently tracked as a member."""
        async with cls.get_connection() as db:
            cursor = await db.execute(
                "SELECT guild_id FROM user_guild_membership WHERE user_id = ?",
                (user_id,),
            )
            rows = await cursor.fetchall()
            return [int(r[0]) for r in rows]

    @classmethod
    async def get_global_verification_state(cls, user_id: int) -> dict | None:
        """Fetch the stored global verification state for a user."""
        async with cls.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT rsi_handle, main_orgs, affiliate_orgs, community_moniker, last_updated
                FROM verification
                WHERE user_id = ?
                """,
                (user_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None

            def _parse_list(val: str | None) -> list[str]:
                if not val:
                    return []
                try:
                    return json.loads(val)
                except Exception:
                    return []

            return {
                "rsi_handle": row[0],
                "main_orgs": _parse_list(row[1]),
                "affiliate_orgs": _parse_list(row[2]),
                "community_moniker": row[3],
                "last_updated": int(row[4]) if row[4] else 0,
            }

    @classmethod
    async def update_global_verification_state(
        cls, user_id: int, state: dict
    ) -> None:
        """Upsert the global verification state in the verification table."""
        async with cls.get_connection() as db:
            await db.execute(
                """
                INSERT INTO verification (
                    user_id, rsi_handle, main_orgs, affiliate_orgs,
                    community_moniker, last_updated, needs_reverify, needs_reverify_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, NULL)
                ON CONFLICT(user_id) DO UPDATE SET
                    rsi_handle = excluded.rsi_handle,
                    main_orgs = excluded.main_orgs,
                    affiliate_orgs = excluded.affiliate_orgs,
                    community_moniker = excluded.community_moniker,
                    last_updated = excluded.last_updated,
                    needs_reverify = 0,
                    needs_reverify_at = NULL
                """,
                (
                    user_id,
                    state.get("rsi_handle", ""),
                    json.dumps(state.get("main_orgs")),
                    json.dumps(state.get("affiliate_orgs")),
                    state.get("community_moniker"),
                    int(state.get("last_updated", 0)),
                ),
            )
            await db.commit()

    @classmethod
    async def purge_voice_data(
        cls, guild_id: int, user_id: int | None = None
    ) -> dict[str, int]:
        """
        Purge all voice-related data for a user or entire guild.

        Args:
            guild_id: The guild ID to purge data for
            user_id: If provided, purge only this user's data. If None, purge all users in guild.

        Returns:
            Dict mapping table names to number of rows deleted.
        """
        deleted_counts = {}

        # Define all voice-related tables to purge with their user column names
        # Using a mapping for security validation
        voice_tables_config = {
            "voice_channels": "owner_id",
            "voice_channel_settings": "owner_id",
            "voice_cooldowns": "user_id",
            "channel_settings": "user_id",
            "channel_permissions": "user_id",
            "channel_ptt_settings": "user_id",
            "channel_priority_speaker_settings": "user_id",
            "channel_soundboard_settings": "user_id",
        }

        async with cls.get_connection() as db:
            # Start transaction
            await db.execute("BEGIN TRANSACTION")

            try:
                for table, user_column in voice_tables_config.items():
                    if user_id is not None:
                        # Delete for specific user in guild - use validated table and column names
                        cursor = await db.execute(
                            f"DELETE FROM {table} WHERE guild_id = ? AND {user_column} = ?",
                            (guild_id, user_id),
                        )
                    else:
                        # Delete all data for guild - table name is validated from whitelist
                        cursor = await db.execute(
                            f"DELETE FROM {table} WHERE guild_id = ?", (guild_id,)
                        )

                    deleted_counts[table] = cursor.rowcount

                await db.commit()
                logger.info(
                    f"Voice data purged for guild {guild_id}, user {user_id}: {deleted_counts}"
                )

            except Exception as e:
                await db.rollback()
                logger.exception("Failed to purge voice data", exc_info=e)
                raise

        return deleted_counts

    @classmethod
    async def cleanup_orphaned_jtc_data(
        cls, guild_id: int, valid_jtc_ids: set[int]
    ) -> dict[str, int]:
        """
        Clean up database rows scoped to JTC IDs that are not in the current guild config.
        This is a defense-in-depth measure for startup reconciliation.

        Args:
            guild_id: The guild ID to clean up
            valid_jtc_ids: Set of JTC channel IDs that are currently configured

        Returns:
            Dict mapping table names to number of rows deleted.
        """
        deleted_counts = {}

        # Define validated whitelist of tables that reference jtc_channel_id
        jtc_tables = {
            "voice_channels",
            "voice_channel_settings",
            "voice_cooldowns",
            "channel_settings",
            "channel_permissions",
            "channel_ptt_settings",
            "channel_priority_speaker_settings",
            "channel_soundboard_settings",
        }

        async with cls.get_connection() as db:
            # Start transaction
            await db.execute("BEGIN TRANSACTION")

            try:
                for table in jtc_tables:
                    if not valid_jtc_ids:
                        # If no valid JTC IDs, delete all JTC-scoped data for this guild
                        # Table name is validated from whitelist above
                        query = f"DELETE FROM {table} WHERE guild_id = ? AND jtc_channel_id IS NOT NULL"
                        cursor = await db.execute(query, (guild_id,))
                    else:
                        # Delete rows where jtc_channel_id is not in the valid set
                        placeholders = ",".join("?" * len(valid_jtc_ids))
                        # Table name is validated from whitelist above
                        query = f"DELETE FROM {table} WHERE guild_id = ? AND jtc_channel_id IS NOT NULL AND jtc_channel_id NOT IN ({placeholders})"
                        cursor = await db.execute(
                            query, [guild_id, *list(valid_jtc_ids)]
                        )

                    deleted_counts[table] = cursor.rowcount

                await db.commit()
                total_deleted = sum(deleted_counts.values())
                if total_deleted > 0:
                    logger.info(
                        f"Orphaned JTC data cleaned up for guild {guild_id}: {total_deleted} rows deleted across tables: {deleted_counts}"
                    )

            except Exception as e:
                await db.rollback()
                logger.exception("Failed to cleanup orphaned JTC data", exc_info=e)
                raise

        return deleted_counts

    @classmethod
    async def purge_stale_jtc_data(
        cls, guild_id: int, stale_jtc_ids: set[int]
    ) -> dict[str, int]:
        """
        Purge voice data for specific stale JTC channel IDs in a guild.

        Args:
            guild_id: The guild ID to purge data for
            stale_jtc_ids: Set of JTC channel IDs that are no longer active

        Returns:
            Dict mapping table names to number of rows deleted.
        """
        if not stale_jtc_ids:
            return {}

        deleted_counts = {}

        # Define validated whitelist of tables that reference jtc_channel_id
        jtc_tables = {
            "voice_channels",
            "voice_channel_settings",
            "voice_cooldowns",
            "channel_settings",
            "channel_permissions",
            "channel_ptt_settings",
            "channel_priority_speaker_settings",
            "channel_soundboard_settings",
        }

        # Convert set to list for SQL IN clause
        jtc_list = list(stale_jtc_ids)
        placeholders = ",".join("?" * len(jtc_list))

        async with cls.get_connection() as db:
            # Start transaction
            await db.execute("BEGIN TRANSACTION")

            try:
                for table in jtc_tables:
                    # Handle voice_cooldowns which doesn't have jtc_channel_id yet in some schemas
                    if table == "voice_cooldowns":
                        # Check if jtc_channel_id column exists - table name is validated from whitelist
                        cursor = await db.execute(f"PRAGMA table_info({table})")
                        columns = [row[1] for row in await cursor.fetchall()]
                        if "jtc_channel_id" not in columns:
                            # Skip voice_cooldowns if it doesn't have jtc_channel_id column
                            deleted_counts[table] = 0
                            continue

                    # Table name is validated from whitelist above
                    query = f"DELETE FROM {table} WHERE guild_id = ? AND jtc_channel_id IN ({placeholders})"
                    cursor = await db.execute(query, [guild_id, *jtc_list])
                    deleted_counts[table] = cursor.rowcount

                await db.commit()
                logger.info(
                    f"Stale JTC data purged for guild {guild_id}, JTC IDs {stale_jtc_ids}: {deleted_counts}"
                )

            except Exception as e:
                await db.rollback()
                logger.exception("Failed to purge stale JTC data", exc_info=e)
                raise

        return deleted_counts

    @classmethod
    async def fetch_audit_logs_by_guild(
        cls, guild_id: str, limit: int = 1000
    ) -> list[dict]:
        """
        Fetch audit log entries for a specific guild.

        Args:
            guild_id: Discord guild ID to filter by
            limit: Maximum number of rows to return (default 1000)

        Returns:
            List of audit log dictionaries with keys:
            - timestamp: Unix timestamp
            - admin_user_id: Discord ID of admin who performed action
            - action: Action type (e.g., "RECHECK_USER", "BULK_RECHECK")
            - target_user_id: Discord ID of target user (may be None)
            - details: JSON string with additional details (may be None)
            - status: Action status (e.g., "success", "error")
        """
        async with cls.get_connection() as db:
            cursor = await db.execute(
                """SELECT timestamp, admin_user_id, action, target_user_id, details, status
                   FROM admin_action_log
                   WHERE guild_id = ?
                   ORDER BY timestamp DESC
                   LIMIT ?""",
                (guild_id, limit),
            )
            rows = await cursor.fetchall()

            # Convert rows to dictionaries
            return [
                {
                    "timestamp": row[0],
                    "admin_user_id": row[1],
                    "action": row[2],
                    "target_user_id": row[3],
                    "details": row[4],
                    "status": row[5],
                }
                for row in rows
            ]

    @classmethod
    async def track_user_guild_membership(
        cls, user_id: int, guild_id: int
    ) -> None:
        """
        Record that a user is active in a guild, updating last_seen timestamp.

        Args:
            user_id: Discord user ID
            guild_id: Discord guild ID
        """
        now = int(time.time())
        async with cls.get_connection() as db:
            await db.execute(
                """
                INSERT INTO user_guild_membership (user_id, guild_id, joined_at, last_seen)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET last_seen = excluded.last_seen
                """,
                (user_id, guild_id, now, now),
            )
            await db.commit()

    @classmethod
    async def remove_user_guild_membership(
        cls, user_id: int, guild_id: int
    ) -> None:
        """
        Remove a user's membership record for a specific guild.

        Args:
            user_id: Discord user ID
            guild_id: Discord guild ID
        """
        async with cls.get_connection() as db:
            await db.execute(
                "DELETE FROM user_guild_membership WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id),
            )
            await db.commit()

    @classmethod
    async def check_rsi_handle_conflict(
        cls, rsi_handle: str, user_id: int
    ) -> int | None:
        """
        Check if an RSI handle is already verified by a different Discord user.

        Args:
            rsi_handle: RSI handle to check (case-insensitive)
            user_id: Discord user ID attempting to verify

        Returns:
            The user_id of the conflicting account, or None if no conflict
        """
        async with cls.get_connection() as db:
            cursor = await db.execute(
                "SELECT user_id FROM verification WHERE LOWER(rsi_handle) = LOWER(?) AND user_id != ?",
                (rsi_handle, user_id),
            )
            row = await cursor.fetchone()
            return row[0] if row else None

    @classmethod
    async def cleanup_guild_specific_data(
        cls, user_id: int, guild_id: int
    ) -> dict[str, int]:
        """
        Remove all guild-specific data for a user in a specific guild.

        This includes voice settings, auto-recheck state, channel settings,
        permissions, etc. Does NOT remove global verification data.

        Args:
            user_id: Discord user ID
            guild_id: Discord guild ID

        Returns:
            Dict mapping table names to number of rows deleted
        """
        deleted_counts = {}

        async with cls.get_connection() as db:
            await db.execute("BEGIN TRANSACTION")
            try:
                # Voice channels owned by user in this guild
                cursor = await db.execute(
                    "DELETE FROM voice_channels WHERE owner_id = ? AND guild_id = ?",
                    (user_id, guild_id),
                )
                deleted_counts["voice_channels"] = cursor.rowcount

                # Voice channel settings
                cursor = await db.execute(
                    "DELETE FROM voice_channel_settings WHERE owner_id = ? AND guild_id = ?",
                    (user_id, guild_id),
                )
                deleted_counts["voice_channel_settings"] = cursor.rowcount

                # Channel settings
                cursor = await db.execute(
                    "DELETE FROM channel_settings WHERE user_id = ? AND guild_id = ?",
                    (user_id, guild_id),
                )
                deleted_counts["channel_settings"] = cursor.rowcount

                # Channel permissions
                cursor = await db.execute(
                    "DELETE FROM channel_permissions WHERE user_id = ? AND guild_id = ?",
                    (user_id, guild_id),
                )
                deleted_counts["channel_permissions"] = cursor.rowcount

                # PTT settings
                cursor = await db.execute(
                    "DELETE FROM channel_ptt_settings WHERE user_id = ? AND guild_id = ?",
                    (user_id, guild_id),
                )
                deleted_counts["channel_ptt_settings"] = cursor.rowcount

                # Priority speaker settings
                cursor = await db.execute(
                    "DELETE FROM channel_priority_speaker_settings WHERE user_id = ? AND guild_id = ?",
                    (user_id, guild_id),
                )
                deleted_counts["channel_priority_speaker_settings"] = cursor.rowcount

                # Soundboard settings
                cursor = await db.execute(
                    "DELETE FROM channel_soundboard_settings WHERE user_id = ? AND guild_id = ?",
                    (user_id, guild_id),
                )
                deleted_counts["channel_soundboard_settings"] = cursor.rowcount

                # Voice cooldowns
                cursor = await db.execute(
                    "DELETE FROM voice_cooldowns WHERE user_id = ? AND guild_id = ?",
                    (user_id, guild_id),
                )
                deleted_counts["voice_cooldowns"] = cursor.rowcount

                # User JTC preferences
                cursor = await db.execute(
                    "DELETE FROM user_jtc_preferences WHERE user_id = ? AND guild_id = ?",
                    (user_id, guild_id),
                )
                deleted_counts["user_jtc_preferences"] = cursor.rowcount

                # Announcement events for this guild
                cursor = await db.execute(
                    "DELETE FROM announcement_events WHERE user_id = ? AND guild_id = ?",
                    (user_id, guild_id),
                )
                deleted_counts["announcement_events"] = cursor.rowcount

                await db.commit()
                logger.info(
                    f"Cleaned up guild-specific data for user {user_id} in guild {guild_id}: {deleted_counts}"
                )
            except Exception:
                await db.rollback()
                raise

        return deleted_counts

    @classmethod
    async def cleanup_all_user_data(cls, user_id: int) -> dict[str, int]:
        """
        Remove ALL data for a user across all guilds, including global verification.

        This is a full cleanup when a user has left all managed guilds.

        Args:
            user_id: Discord user ID

        Returns:
            Dict mapping table names to number of rows deleted
        """
        deleted_counts = {}

        async with cls.get_connection() as db:
            await db.execute("BEGIN TRANSACTION")
            try:
                # Global verification record
                cursor = await db.execute(
                    "DELETE FROM verification WHERE user_id = ?",
                    (user_id,),
                )
                deleted_counts["verification"] = cursor.rowcount

                # Auto-recheck state
                cursor = await db.execute(
                    "DELETE FROM auto_recheck_state WHERE user_id = ?",
                    (user_id,),
                )
                deleted_counts["auto_recheck_state"] = cursor.rowcount

                # Rate limits
                cursor = await db.execute(
                    "DELETE FROM rate_limits WHERE user_id = ?",
                    (user_id,),
                )
                deleted_counts["rate_limits"] = cursor.rowcount

                # Voice channels (all guilds)
                cursor = await db.execute(
                    "DELETE FROM voice_channels WHERE owner_id = ?",
                    (user_id,),
                )
                deleted_counts["voice_channels"] = cursor.rowcount

                # Voice channel settings (all guilds)
                cursor = await db.execute(
                    "DELETE FROM voice_channel_settings WHERE owner_id = ?",
                    (user_id,),
                )
                deleted_counts["voice_channel_settings"] = cursor.rowcount

                # Channel settings (all guilds)
                cursor = await db.execute(
                    "DELETE FROM channel_settings WHERE user_id = ?",
                    (user_id,),
                )
                deleted_counts["channel_settings"] = cursor.rowcount

                # Channel permissions (all guilds)
                cursor = await db.execute(
                    "DELETE FROM channel_permissions WHERE user_id = ?",
                    (user_id,),
                )
                deleted_counts["channel_permissions"] = cursor.rowcount

                # PTT settings (all guilds)
                cursor = await db.execute(
                    "DELETE FROM channel_ptt_settings WHERE user_id = ?",
                    (user_id,),
                )
                deleted_counts["channel_ptt_settings"] = cursor.rowcount

                # Priority speaker settings (all guilds)
                cursor = await db.execute(
                    "DELETE FROM channel_priority_speaker_settings WHERE user_id = ?",
                    (user_id,),
                )
                deleted_counts["channel_priority_speaker_settings"] = cursor.rowcount

                # Soundboard settings (all guilds)
                cursor = await db.execute(
                    "DELETE FROM channel_soundboard_settings WHERE user_id = ?",
                    (user_id,),
                )
                deleted_counts["channel_soundboard_settings"] = cursor.rowcount

                # Voice cooldowns (all guilds)
                cursor = await db.execute(
                    "DELETE FROM voice_cooldowns WHERE user_id = ?",
                    (user_id,),
                )
                deleted_counts["voice_cooldowns"] = cursor.rowcount

                # User JTC preferences (all guilds)
                cursor = await db.execute(
                    "DELETE FROM user_jtc_preferences WHERE user_id = ?",
                    (user_id,),
                )
                deleted_counts["user_jtc_preferences"] = cursor.rowcount

                # Announcement events (all guilds)
                cursor = await db.execute(
                    "DELETE FROM announcement_events WHERE user_id = ?",
                    (user_id,),
                )
                deleted_counts["announcement_events"] = cursor.rowcount

                # Guild membership tracking
                cursor = await db.execute(
                    "DELETE FROM user_guild_membership WHERE user_id = ?",
                    (user_id,),
                )
                deleted_counts["user_guild_membership"] = cursor.rowcount

                await db.commit()
                logger.info(
                    f"Cleaned up all data for user {user_id}: {deleted_counts}"
                )
            except Exception:
                await db.rollback()
                raise

        return deleted_counts

