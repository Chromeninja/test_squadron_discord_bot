import types
from contextlib import asynccontextmanager

import pytest

from helpers.announcement import _classify_event, enqueue_verification_event
from services.db import repository as repo_module


@pytest.mark.parametrize(
    "old_status,new_status,expected",
    [
        ("non_member", "affiliate", "joined_affiliate"),
        ("non_member", "main", "joined_main"),
        ("affiliate", "main", "promoted_to_main"),
        ("unknown", "main", "joined_main"),
    ],
)
def test_classify_promotions(old_status, new_status, expected):
    assert _classify_event(old_status, new_status) == expected


@pytest.mark.parametrize(
    "old_status,new_status",
    [
        ("main", "affiliate"),
        ("main", "non_member"),
        ("affiliate", "non_member"),
        ("main", "main"),
    ],
)
def test_classify_demotions_or_noops(old_status, new_status):
    assert _classify_event(old_status, new_status) is None


@pytest.mark.asyncio
async def test_enqueue_verification_event_skips_unannounceable(monkeypatch):
    calls: list[tuple[str, tuple]] = []

    @asynccontextmanager
    async def fake_txn():
        class DummyDB:
            async def execute(self, sql, params):
                calls.append((sql, params))

        yield DummyDB()

    monkeypatch.setattr(repo_module.BaseRepository, "transaction", fake_txn)

    member = types.SimpleNamespace(id=10, guild=types.SimpleNamespace(id=20))

    await enqueue_verification_event(member, "main", "affiliate")  # type: ignore[arg-type]

    assert calls == []


@pytest.mark.asyncio
async def test_enqueue_verification_event_coalesces_and_inserts(monkeypatch):
    calls: list[tuple[str, tuple]] = []

    @asynccontextmanager
    async def fake_txn():
        class DummyDB:
            async def execute(self, sql, params):
                calls.append((sql, params))

        yield DummyDB()

    monkeypatch.setattr(repo_module.BaseRepository, "transaction", fake_txn)

    member = types.SimpleNamespace(id=111, guild=types.SimpleNamespace(id=222))

    await enqueue_verification_event(member, "non_member", "main")  # type: ignore[arg-type]

    assert len(calls) == 2

    delete_sql, delete_params = calls[0]
    assert "DELETE FROM announcement_events" in delete_sql
    assert delete_params == (111, 222)

    insert_sql, insert_params = calls[1]
    assert "INSERT INTO announcement_events" in insert_sql
    assert insert_params[0] == 111
    assert insert_params[1] == 222
    assert insert_params[4] == "joined_main"
