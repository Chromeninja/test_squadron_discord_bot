import argparse
import asyncio
import signal

from bot import MyBot, intents, PREFIX
from helpers.database import Database

async def main():
    parser = argparse.ArgumentParser(description="Dev smoke startup for cogs/extensions.")
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Seconds to wait before shutdown. If omitted, waits for Ctrl+C.",
    )
    args = parser.parse_args()

    await Database.initialize()
    bot = MyBot(command_prefix=PREFIX, intents=intents)

    stop_event = asyncio.Event()

    def _signal_handler():
        stop_event.set()

    loop = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(s, _signal_handler)
        except NotImplementedError:
            pass  # Non-UNIX platforms

    try:
        await bot.setup_hook()  # Load extensions/cogs only; no Discord connection
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
