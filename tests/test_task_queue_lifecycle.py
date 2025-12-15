import asyncio
import importlib
import sys
import types

import pytest


@pytest.mark.asyncio
async def test_task_queue_workers_start_and_stop(monkeypatch):
    """Bot setup_hook starts workers and close() stops them; backend stays read-only."""

    # Prevent bot.run at import time and satisfy token requirement
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("TESTBOT_DRY_RUN", "1")

    # Import (or reload) the bot module so patches apply cleanly
    bot_mod = importlib.reload(sys.modules["bot"]) if "bot" in sys.modules else importlib.import_module("bot")

    calls: list[tuple[str, object]] = []

    # Stubs for task queue lifecycle
    async def fake_start_task_workers(num_workers: int = 2) -> None:
        calls.append(("start", num_workers))

    async def fake_stop_task_workers() -> None:
        calls.append(("stop", None))

    monkeypatch.setattr(bot_mod, "start_task_workers", fake_start_task_workers)
    monkeypatch.setattr(bot_mod, "stop_task_workers", fake_stop_task_workers)

    # Stub external dependencies invoked during setup/teardown
    class FakeHTTPClient:
        def __init__(self, *args, **kwargs):
            pass

        async def _get_session(self):
            return None

        async def close(self):
            return None

    class FakeServiceContainer:
        def __init__(self, *args, **kwargs):
            self.config = None

        async def initialize(self):
            return None

        async def cleanup(self):
            return None

    class FakeInternalAPI:
        def __init__(self, services):
            self.services = services

        async def start(self):
            return None

        async def stop(self):
            return None

    class FakeBulkAnnouncer:
        def __init__(self, bot):
            self.bot = bot

    async def async_noop(*_args, **_kwargs):
        return None

    def sync_noop(*_args, **_kwargs):
        return None

    # Apply patches before instantiation
    monkeypatch.setattr(bot_mod, "HTTPClient", FakeHTTPClient)

    # Patch imports resolved inside setup_hook
    import helpers.announcement as ha
    import services.db.database as db_mod
    import services.internal_api as ia
    import services.service_container as sc

    monkeypatch.setattr(sc, "ServiceContainer", FakeServiceContainer)
    monkeypatch.setattr(ia, "InternalAPIServer", FakeInternalAPI)
    monkeypatch.setattr(ha, "BulkAnnouncer", FakeBulkAnnouncer)
    monkeypatch.setattr(db_mod, "Database", types.SimpleNamespace(initialize=async_noop))
    monkeypatch.setattr(bot_mod, "spawn", lambda coro: asyncio.create_task(coro))

    # Patch bot methods that would hit external systems
    monkeypatch.setattr(bot_mod.MyBot, "add_cog", async_noop)
    monkeypatch.setattr(bot_mod.MyBot, "load_extension", async_noop)
    monkeypatch.setattr(bot_mod.MyBot, "_track_task", sync_noop)
    monkeypatch.setattr(bot_mod.MyBot, "cache_roles", async_noop)
    monkeypatch.setattr(bot_mod.MyBot, "role_refresh_task", async_noop)
    monkeypatch.setattr(bot_mod.MyBot, "token_cleanup_task", async_noop)
    monkeypatch.setattr(bot_mod.MyBot, "attempts_cleanup_task", async_noop)
    monkeypatch.setattr(bot_mod.MyBot, "log_cleanup_task", async_noop)
    monkeypatch.setattr(bot_mod.MyBot, "add_view", sync_noop)
    # Provide resolved application info once awaited
    app_info_future = asyncio.Future()
    app_info_future.set_result(
        types.SimpleNamespace(owner=types.SimpleNamespace(id=123, name="owner"), team=None)
    )
    monkeypatch.setattr(bot_mod.MyBot, "application_info", lambda self: app_info_future)

    # Use get_prefix() for lazy-loaded prefix access
    bot_instance = bot_mod.MyBot(command_prefix=bot_mod.get_prefix(), intents=bot_mod.intents)

    # Stub tree methods on the existing command tree instance
    monkeypatch.setattr(bot_instance.tree, "sync", async_noop)
    monkeypatch.setattr(bot_instance.tree, "walk_commands", lambda: [])

    await bot_instance.setup_hook()

    assert ("start", 2) in calls
    assert ("stop", None) not in calls

    await bot_instance.close()

    assert ("stop", None) in calls
    assert bot_instance._background_tasks == set()
