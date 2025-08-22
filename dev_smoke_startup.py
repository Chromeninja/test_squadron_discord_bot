# dev_smoke_startup.py — DRY RUN SAFE
# - Loads extensions without logging in
# - Suppresses discord.ext.tasks loops and any bot.loop.create_task()
# - Clean shutdown on Ctrl+C without touching global workers/HTTP

import argparse
import asyncio
import signal
import os
from types import SimpleNamespace

from discord.ext import commands as dcommands, tasks as dctasks

from bot import MyBot, intents, PREFIX, initial_extensions
from helpers.database import Database


# --- 1) Suppress discord.ext.tasks loops in dry run --------------------------
_ORIG_LOOP_START = dctasks.Loop.start

def _dry_run_loop_start(self, *args, **kwargs):  # noqa: N802
    # Don't schedule the task loop at all during dry runs
    coro_name = getattr(self.coro, "__name__", "unknown")
    print(f"[DRY-RUN] Suppressed tasks.Loop.start() for '{coro_name}'")
    # Pretend it's not running; callers typically don't inspect the returned task
    return None

# Install the monkeypatch up-front so cogs see it when they import/start
dctasks.Loop.start = _dry_run_loop_start


# --- 2) A fake loop that swallows create_task() calls ------------------------
class _DryLoop:
    def create_task(self, coro):
        # Do NOT schedule background jobs in dry run
        name = getattr(getattr(coro, "cr_code", None), "co_name", None) or getattr(coro, "__name__", repr(coro))
        print(f"[DRY-RUN] Suppressed loop.create_task() for '{name}'")
        # Return a dummy object with cancel() to satisfy code that might call it
        return SimpleNamespace(cancel=lambda: None)


class DryRunBot(MyBot):
    async def setup_hook(self):
        # Give cogs a 'loop' that we control (overrides discord.py's loop property)
        # This prevents calls like self.bot.loop.create_task(...) from actually scheduling.
        self.loop = _DryLoop()  # type: ignore[attr-defined]

        # Only load extensions; skip workers, HTTP session, sync, etc.
        for ext in initial_extensions:
            try:
                await self.load_extension(ext)
                print(f"[DRY-RUN] Loaded extension: {ext}")
            except Exception as e:
                print(f"[DRY-RUN] Failed to load {ext}: {e}")

        print("[DRY-RUN] setup_hook complete (no login performed)")

    async def close(self):
        # Unload extensions so cog unload hooks can run, but
        # DO NOT touch global task_queue or aiohttp session.
        for ext in list(self.extensions.keys()):
            try:
                await self.unload_extension(ext)
            except Exception:
                pass
        # Bypass MyBot.close() (which enqueues None to task_queue & awaits join)
        await dcommands.Bot.close(self)


async def main():
    parser = argparse.ArgumentParser(description="Dry-run loader for extensions/cogs (no Discord connection).")
    parser.add_argument("--timeout", type=float, default=None, help="Seconds to wait before shutdown (Ctrl+C otherwise).")
    args = parser.parse_args()

    # Make the intent explicit for downstream checks if you later add them
    os.environ["TESTBOT_DRY_RUN"] = "1"

    await Database.initialize()

    bot = DryRunBot(command_prefix=PREFIX, intents=intents)

    stop_event = asyncio.Event()

    def _signal_handler():
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass  # e.g., on Windows

    try:
        await bot.setup_hook()  # Only load cogs; no login
        print("SETUP_OK")
        if args.timeout and args.timeout > 0:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=args.timeout)
                print("SHUTDOWN_SIGNAL")
            except asyncio.TimeoutError:
                print("TIMEOUT_SHUTDOWN")
        else:
            await stop_event.wait()
            print("SHUTDOWN_SIGNAL")
    finally:
        await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
