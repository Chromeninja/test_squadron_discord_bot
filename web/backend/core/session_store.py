"""
SQLite-backed server-side session store.

Replaces the in-memory ``dict`` previously used in ``security.py`` so that
sessions survive process restarts and are bounded by automatic expiry.

The store uses its own lightweight SQLite database (``sessions.db``) kept
alongside the main bot database to avoid schema coupling.  All public
helpers are *async* but the module gracefully degrades to a temporary
in-memory SQLite instance when ``initialize()`` has not been called (handy
for unit tests).

Thread-safety: aiosqlite serialises writes; concurrent readers are fine
under WAL mode.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_db_path: str | None = None
_initialized: bool = False
_init_lock: asyncio.Lock | None = None

# Shared in-memory connection (only used when _db_path == ":memory:")
_memory_conn: aiosqlite.Connection | None = None
_memory_conn_loop: asyncio.AbstractEventLoop | None = None

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id  TEXT PRIMARY KEY,
    data        TEXT    NOT NULL,
    created_at  REAL    NOT NULL,
    expires_at  REAL    NOT NULL
)
"""
_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions (expires_at)
"""

# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def _get_lock() -> asyncio.Lock:
    """Return the init lock, creating it in the current event loop if needed."""
    global _init_lock
    if _init_lock is None:
        _init_lock = asyncio.Lock()
    return _init_lock


async def initialize(db_path: str | Path | None = None) -> None:
    """Create the sessions table if it doesn't exist.

    Parameters
    ----------
    db_path:
        File path for the session SQLite database.  When *None* an in-memory
        database is used (useful for tests).
    """
    global _db_path, _initialized, _memory_conn, _memory_conn_loop

    async with _get_lock():
        if _initialized:
            return

        _db_path = str(db_path) if db_path else ":memory:"

        if _db_path == ":memory:":
            # Keep a single shared connection for in-memory mode so that all
            # callers see the same database.
            _memory_conn = await aiosqlite.connect(":memory:")
            await _memory_conn.execute(_CREATE_TABLE)
            await _memory_conn.execute(_CREATE_INDEX)
            await _memory_conn.commit()
            _memory_conn_loop = asyncio.get_running_loop()
        else:
            async with aiosqlite.connect(_db_path) as db:
                await db.execute("PRAGMA journal_mode=WAL")
                await db.execute("PRAGMA synchronous=NORMAL")
                await db.execute(_CREATE_TABLE)
                await db.execute(_CREATE_INDEX)
                await db.commit()

        _initialized = True
        logger.info("Session store initialized", extra={"db_path": _db_path})


async def close() -> None:
    """Shut down the store and release resources."""
    global _initialized, _memory_conn, _memory_conn_loop, _init_lock
    if _memory_conn is not None:
        await _memory_conn.close()
        _memory_conn = None
    _memory_conn_loop = None
    _initialized = False
    _init_lock = None  # recreate in the next event loop


async def _ensure_memory_conn_for_current_loop() -> None:
    """Recreate in-memory connection when pytest/event loop scope changes."""
    global _memory_conn, _memory_conn_loop

    if _db_path != ":memory:":
        return

    current_loop = asyncio.get_running_loop()
    if _memory_conn is not None and _memory_conn_loop is current_loop:
        return

    async with _get_lock():
        current_loop = asyncio.get_running_loop()
        if _memory_conn is not None and _memory_conn_loop is current_loop:
            return

        if _memory_conn is not None:
            with contextlib.suppress(Exception):
                await _memory_conn.close()

        _memory_conn = await aiosqlite.connect(":memory:")
        await _memory_conn.execute(_CREATE_TABLE)
        await _memory_conn.execute(_CREATE_INDEX)
        await _memory_conn.commit()
        _memory_conn_loop = current_loop


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _connect():
    """Yield an aiosqlite connection configured for the session DB.

    For in-memory databases we reuse the shared connection so that all
    operations hit the same data.  For file-backed databases each caller
    gets its own short-lived connection.
    """
    if _db_path == ":memory:":
        await _ensure_memory_conn_for_current_loop()

    if _memory_conn is not None:
        # Shared in-memory connection — do NOT close it on exit.
        yield _memory_conn
        return

    path = _db_path or ":memory:"
    async with aiosqlite.connect(path) as db:
        await db.execute("PRAGMA busy_timeout=3000")
        yield db


async def _ensure_schema() -> None:
    """Lazy-init for callers that skip ``initialize()`` (e.g. tests)."""
    if _initialized:
        return
    await initialize()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def save(session_id: str, data: dict, created_at: float, expires_at: float) -> None:
    """Persist *or* update a session record."""
    await _ensure_schema()
    async with _connect() as db:
        await db.execute(
            """
            INSERT INTO sessions (session_id, data, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                data = excluded.data,
                created_at = excluded.created_at,
                expires_at = excluded.expires_at
            """,
            (session_id, json.dumps(data), created_at, expires_at),
        )
        await db.commit()


@dataclass
class SessionRow:
    """Lightweight mirror of a stored session."""
    data: dict
    created_at: float
    expires_at: float


async def load(session_id: str) -> SessionRow | None:
    """Return the session for *session_id* or ``None`` if missing / expired."""
    await _ensure_schema()
    now = time.time()
    async with _connect() as db:
        cur = await db.execute(
            "SELECT data, created_at, expires_at FROM sessions WHERE session_id = ? AND expires_at > ?",
            (session_id, now),
        )
        row = await cur.fetchone()
        if row is None:
            return None
        return SessionRow(
            data=json.loads(row[0]),
            created_at=row[1],
            expires_at=row[2],
        )


async def delete(session_id: str) -> None:
    """Remove a single session."""
    await _ensure_schema()
    async with _connect() as db:
        await db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        await db.commit()


async def cleanup_expired() -> int:
    """Delete all expired sessions.  Returns the number of rows removed."""
    await _ensure_schema()
    now = time.time()
    async with _connect() as db:
        cur = await db.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        await db.commit()
        return cur.rowcount  # type: ignore[return-value]
