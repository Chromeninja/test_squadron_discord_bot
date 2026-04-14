"""Tests for task queue retry logic including 429 rate-limit handling."""

import discord
import pytest

from helpers.task_queue import run_task


@pytest.mark.asyncio
async def test_run_task_retries_on_5xx(monkeypatch) -> None:
    """Task should retry on 5xx DiscordServerError."""
    calls = 0

    async def failing_task() -> str:
        nonlocal calls
        calls += 1
        if calls < 2:
            exc = discord.HTTPException(
                _FakeResponse(status=500),
                {"message": "Internal Server Error"},
            )
            exc.status = 500
            raise exc
        return "ok"

    monkeypatch.setattr("helpers.task_queue.secure_uniform", lambda a, b: 0.0)
    result = await run_task(failing_task)

    assert result == "ok"
    assert calls == 2


@pytest.mark.asyncio
async def test_run_task_retries_on_429_with_retry_after(monkeypatch) -> None:
    """Task should retry on 429 HTTPException using Retry-After delay."""
    calls = 0

    async def rate_limited_task() -> str:
        nonlocal calls
        calls += 1
        if calls < 2:
            exc = discord.HTTPException(
                _FakeResponse(status=429),
                {"message": "Rate limited", "retry_after": 0.01},
            )
            exc.status = 429
            exc.retry_after = 0.01
            raise exc
        return "done"

    monkeypatch.setattr("helpers.task_queue.secure_uniform", lambda a, b: 0.0)
    result = await run_task(rate_limited_task)

    assert result == "done"
    assert calls == 2


@pytest.mark.asyncio
async def test_run_task_gives_up_after_max_retries(monkeypatch) -> None:
    """Task should give up after MAX_RETRIES attempts."""
    calls = 0

    async def always_failing() -> str:
        nonlocal calls
        calls += 1
        exc = discord.HTTPException(
            _FakeResponse(status=500),
            {"message": "Always fails"},
        )
        exc.status = 500
        raise exc

    monkeypatch.setattr("helpers.task_queue.secure_uniform", lambda a, b: 0.0)
    result = await run_task(always_failing)

    assert result is None
    assert calls == 3  # MAX_RETRIES = 3


@pytest.mark.asyncio
async def test_run_task_does_not_retry_on_400(monkeypatch) -> None:
    """Task should not retry on client errors like 400."""
    calls = 0

    async def client_error_task() -> str:
        nonlocal calls
        calls += 1
        exc = discord.HTTPException(
            _FakeResponse(status=400),
            {"message": "Bad Request"},
        )
        exc.status = 400
        raise exc

    monkeypatch.setattr("helpers.task_queue.secure_uniform", lambda a, b: 0.0)
    result = await run_task(client_error_task)

    assert result is None
    assert calls == 1  # No retry


class _FakeResponse:
    """Minimal fake aiohttp response for discord.HTTPException."""

    def __init__(self, status: int) -> None:
        self.status = status
        self.reason = "Test"
        self.headers = {"Content-Type": "application/json"}
