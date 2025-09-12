import time
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from helpers import rate_limiter as rl


@pytest_asyncio.fixture(autouse=True)
async def patch_db(monkeypatch) -> None:
    # Patch Database methods used by rate limiter
    fetch = AsyncMock(return_value=None)
    incr = AsyncMock()
    reset = AsyncMock()
    monkeypatch.setattr("helpers.rate_limiter.Database.fetch_rate_limit", fetch)
    monkeypatch.setattr("helpers.rate_limiter.Database.increment_rate_limit", incr)
    monkeypatch.setattr("helpers.rate_limiter.Database.reset_rate_limit", reset)
    yield fetch, incr, reset


@pytest.mark.asyncio
async def test_check_rate_limit_within_window(monkeypatch, patch_db) -> None:
    fetch, _incr, _reset = patch_db
    now = int(time.time())
    # 1 attempt within window; should not be rate-limited
    fetch.return_value = (1, now)
    rl.MAX_ATTEMPTS = 5
    rl.RATE_LIMIT_WINDOW = 100
    limited, wait_until = await rl.check_rate_limit(1, "verification")
    assert limited is False
    assert wait_until == 0


@pytest.mark.asyncio
async def test_check_rate_limit_hit(monkeypatch, patch_db) -> None:
    fetch, _incr, _reset = patch_db
    now = int(time.time())
    fetch.return_value = (5, now)
    rl.MAX_ATTEMPTS = 5
    rl.RATE_LIMIT_WINDOW = 100
    limited, wait_until = await rl.check_rate_limit(1, "verification")
    assert limited is True
    assert wait_until == now + 100


@pytest.mark.asyncio
async def test_check_rate_limit_reset_after_window(monkeypatch, patch_db) -> None:
    fetch, _incr, reset = patch_db
    then = int(time.time()) - 1000
    rl.RATE_LIMIT_WINDOW = 100
    fetch.return_value = (5, then)
    limited, wait_until = await rl.check_rate_limit(1, "verification")
    assert limited is False
    assert wait_until == 0
    reset.assert_awaited()


@pytest.mark.asyncio
async def test_log_and_reset_attempts(patch_db) -> None:
    _fetch, incr, reset = patch_db
    await rl.log_attempt(2, "verification")
    incr.assert_awaited()
    await rl.reset_attempts(2)
    reset.assert_awaited()


@pytest.mark.asyncio
async def test_get_remaining_attempts(monkeypatch, patch_db) -> None:
    fetch, _incr, _reset = patch_db
    rl.MAX_ATTEMPTS = 5
    now = int(time.time())
    rl.RATE_LIMIT_WINDOW = 100
    # No record
    fetch.return_value = None
    assert await rl.get_remaining_attempts(1, "verification") == 5
    # Within window with 2 attempts
    fetch.return_value = (2, now)
    assert await rl.get_remaining_attempts(1, "verification") == 3
    # Expired window resets to max
    fetch.return_value = (5, now - 1000)
    assert await rl.get_remaining_attempts(1, "verification") == 5


@pytest.mark.asyncio
async def test_cleanup_attempts(monkeypatch) -> None:
    # Use a simple in-memory DB call path, patch Database.get_connection
    class FakeCursor:
        async def execute(self, *args, **kwargs) -> None:
            return None

        async def commit(self) -> None:
            return None

    class Ctx:
        async def __aenter__(self) -> None:
            return FakeCursor()

        async def __aexit__(self, *args) -> None:
            return False

    def fake_conn() -> None:
        return Ctx()

    monkeypatch.setattr("helpers.rate_limiter.Database.get_connection", fake_conn)
    # Should not raise
    await rl.cleanup_attempts()
