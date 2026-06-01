"""Shared fixtures for backend/ tests.

Reuses the `temp_db` fixture from the top-level tests/conftest.py so backend
repository tests run against a real, isolated SQLite database initialised from
services/db/schema.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest_asyncio

# Ensure project root is importable when pytest is invoked from backend/.
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.db.database import Database


@pytest_asyncio.fixture()
async def temp_db(tmp_path):
    """Initialise Database to a temporary file for isolation across tests."""
    orig_path = Database._db_path
    orig_initialized = Database._initialized

    Database._initialized = False
    Database._db_path = None  # type: ignore[assignment]
    db_file = tmp_path / "test.db"
    await Database.initialize(str(db_file))

    assert Database._initialized is True
    assert Database._db_path == str(db_file)

    yield str(db_file)

    Database._db_path = orig_path
    Database._initialized = orig_initialized
