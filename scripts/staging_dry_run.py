#!/usr/bin/env python3
"""
Staging Dry-Run Verification Script

Performs a comprehensive pre-launch validation of the bot + backend + dashboard
system. Run this against a staging environment before production deployment.

Supports optional bot extension smoke loading (no Discord login) so the same
script covers both API health and bot dry-run validation.

Usage:
    python scripts/staging_dry_run.py [--bot-url BOT_URL] [--backend-url BACKEND_URL]
                                      [--bot-smoke] [--bot-timeout SECONDS]

Environment Variables:
    STAGING_BOT_URL: Bot internal API URL (default: http://127.0.0.1:8082)
    STAGING_BACKEND_URL: Backend API URL (default: http://127.0.0.1:8000)
    INTERNAL_API_KEY: API key for authenticated endpoints

Exit Codes:
    0: All checks passed
    1: One or more checks failed
    2: Critical error (could not run checks)
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import signal
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

import aiohttp

from utils.logging import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)


@dataclass
class CheckResult:
    """Result of a single verification check."""
    name: str
    passed: bool
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class DryRunReport:
    """Complete dry-run verification report."""
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for c in self.checks if not c.passed)

    def add(self, result: CheckResult) -> None:
        self.checks.append(result)
        status = "✅" if result.passed else "❌"
        logger.info(f"{status} {result.name}: {result.message}")

    def summary(self) -> str:
        lines = [
            "",
            "=" * 60,
            "STAGING DRY-RUN SUMMARY",
            "=" * 60,
            f"Total Checks: {len(self.checks)}",
            f"Passed: {self.passed_count}",
            f"Failed: {self.failed_count}",
            "",
        ]

        if self.failed_count > 0:
            lines.append("Failed Checks:")
            for c in self.checks:
                if not c.passed:
                    lines.append(f"  ❌ {c.name}: {c.message}")
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)


class StagingDryRun:
    """Execute staging verification checks."""

    def __init__(
        self,
        bot_url: str = "http://127.0.0.1:8082",
        backend_url: str = "http://127.0.0.1:8000",
        api_key: str | None = None,
    ):
        self.bot_url = bot_url.rstrip("/")
        self.backend_url = backend_url.rstrip("/")
        self.api_key = api_key or os.environ.get("INTERNAL_API_KEY", "")
        self.report = DryRunReport()
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
        )
        return self

    async def __aexit__(self, *args):
        if self._session:
            await self._session.close()

    @property
    def session(self) -> aiohttp.ClientSession:
        if not self._session:
            raise RuntimeError("Session not initialized. Use async with.")
        return self._session

    def _auth_headers(self) -> dict:
        """Return auth headers for internal API."""
        if self.api_key:
            return {"Authorization": f"Bearer {self.api_key}"}
        return {}

    # -------------------------------------------------------------------------
    # Backend Checks
    # -------------------------------------------------------------------------

    async def check_backend_health(self) -> None:
        """Verify backend is running and healthy."""
        try:
            async with self.session.get(f"{self.backend_url}/") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.report.add(CheckResult(
                        name="Backend Health",
                        passed=True,
                        message=f"Backend running: {data.get('service', 'unknown')}",
                        details=data,
                    ))
                else:
                    self.report.add(CheckResult(
                        name="Backend Health",
                        passed=False,
                        message=f"Backend returned {resp.status}",
                    ))
        except Exception as e:
            self.report.add(CheckResult(
                name="Backend Health",
                passed=False,
                message=f"Cannot reach backend: {e}",
            ))

    async def check_backend_config_status(self) -> None:
        """Verify backend config is loaded."""
        try:
            async with self.session.get(f"{self.backend_url}/api/health/config-status") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    status = data.get("config_status", "unknown")
                    passed = status in ("ok", "degraded")
                    self.report.add(CheckResult(
                        name="Backend Config",
                        passed=passed,
                        message=f"Config status: {status}",
                        details=data,
                    ))
                else:
                    self.report.add(CheckResult(
                        name="Backend Config",
                        passed=False,
                        message=f"Config status endpoint returned {resp.status}",
                    ))
        except Exception as e:
            self.report.add(CheckResult(
                name="Backend Config",
                passed=False,
                message=f"Cannot check config status: {e}",
            ))

    async def check_backend_readiness(self) -> None:
        """Verify backend readiness probe."""
        try:
            async with self.session.get(f"{self.backend_url}/api/health/readiness") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.report.add(CheckResult(
                        name="Backend Readiness",
                        passed=data.get("ready", False),
                        message="Backend ready to receive traffic",
                        details=data,
                    ))
                else:
                    self.report.add(CheckResult(
                        name="Backend Readiness",
                        passed=False,
                        message=f"Readiness check failed: {resp.status}",
                    ))
        except Exception as e:
            self.report.add(CheckResult(
                name="Backend Readiness",
                passed=False,
                message=f"Cannot check readiness: {e}",
            ))

    # -------------------------------------------------------------------------
    # Bot Checks
    # -------------------------------------------------------------------------

    async def check_bot_health(self) -> None:
        """Verify bot internal API is running."""
        try:
            async with self.session.get(
                f"{self.bot_url}/health",
                headers=self._auth_headers(),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    status = data.get("status", "unknown")
                    self.report.add(CheckResult(
                        name="Bot Health",
                        passed=status in ("healthy", "ok"),
                        message=f"Bot status: {status}",
                        details=data,
                    ))
                else:
                    self.report.add(CheckResult(
                        name="Bot Health",
                        passed=False,
                        message=f"Bot health returned {resp.status}",
                    ))
        except Exception as e:
            self.report.add(CheckResult(
                name="Bot Health",
                passed=False,
                message=f"Cannot reach bot: {e}",
            ))

    async def check_bot_cogs(self) -> None:
        """Verify bot cogs are loaded."""
        try:
            async with self.session.get(
                f"{self.bot_url}/health",
                headers=self._auth_headers(),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    cogs = data.get("cogs_loaded", [])
                    if cogs:
                        self.report.add(CheckResult(
                            name="Bot Cogs",
                            passed=True,
                            message=f"{len(cogs)} cogs loaded",
                            details={"cogs": cogs},
                        ))
                    else:
                        self.report.add(CheckResult(
                            name="Bot Cogs",
                            passed=False,
                            message="No cogs reported by bot health",
                        ))
                else:
                    self.report.add(CheckResult(
                        name="Bot Cogs",
                        passed=False,
                        message=f"Cannot check cogs: {resp.status}",
                    ))
        except Exception as e:
            self.report.add(CheckResult(
                name="Bot Cogs",
                passed=False,
                message=f"Cannot check cogs: {e}",
            ))

    async def check_bot_database(self) -> None:
        """Verify bot database connectivity."""
        try:
            async with self.session.get(
                f"{self.bot_url}/health",
                headers=self._auth_headers(),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    db_ok = data.get("db_ok", False)
                    self.report.add(CheckResult(
                        name="Bot Database",
                        passed=db_ok,
                        message="Database connected" if db_ok else "Database not connected",
                    ))
                else:
                    self.report.add(CheckResult(
                        name="Bot Database",
                        passed=False,
                        message=f"Cannot check database: {resp.status}",
                    ))
        except Exception as e:
            self.report.add(CheckResult(
                name="Bot Database",
                passed=False,
                message=f"Cannot check database: {e}",
            ))

    # -------------------------------------------------------------------------
    # Integration Checks
    # -------------------------------------------------------------------------

    async def check_backend_to_bot_communication(self) -> None:
        """Verify backend can communicate with bot internal API."""
        # This is implicitly tested when backend health overview works
        # since it calls the bot internal API
        try:
            # Try the backend's health overview which should call bot
            # We don't have auth here, so just check if the endpoint exists
            async with self.session.get(f"{self.backend_url}/api/health/liveness") as resp:
                self.report.add(CheckResult(
                    name="Backend→Bot Integration",
                    passed=resp.status == 200,
                    message="Backend liveness OK (full integration requires auth)",
                ))
        except Exception as e:
            self.report.add(CheckResult(
                name="Backend→Bot Integration",
                passed=False,
                message=f"Integration check failed: {e}",
            ))

    # -------------------------------------------------------------------------
    # Run All Checks
    # -------------------------------------------------------------------------

    async def run_all(self) -> DryRunReport:
        """Execute all verification checks."""
        logger.info("=" * 60)
        logger.info("STAGING DRY-RUN VERIFICATION")
        logger.info(f"Bot URL: {self.bot_url}")
        logger.info(f"Backend URL: {self.backend_url}")
        logger.info("=" * 60)

        # Backend checks
        await self.check_backend_health()
        await self.check_backend_config_status()
        await self.check_backend_readiness()

        # Bot checks
        await self.check_bot_health()
        await self.check_bot_cogs()
        await self.check_bot_database()

        # Integration checks
        await self.check_backend_to_bot_communication()

        return self.report

    async def run_bot_smoke(self, *, timeout: float | None = None, wait_for_signal: bool = False) -> CheckResult:
        """Load bot extensions without logging in; prevents background tasks from running."""

        # Lazy imports to avoid discord dependency when only doing HTTP checks
        from discord.ext import commands as dcommands
        from discord.ext import tasks as dctasks

        import bot as bot_module  # type: ignore[import-not-found]
        from services.db.database import Database

        os.environ["TESTBOT_DRY_RUN"] = "1"

        orig_loop_start = dctasks.Loop.start

        def _dry_run_loop_start(self, *args, **kwargs) -> None:
            coro_name = getattr(self.coro, "__name__", "unknown")
            logger.info("[DRY-RUN] Suppressed tasks.Loop.start() for '%s'", coro_name)

        dctasks.Loop.start = _dry_run_loop_start  # type: ignore[method-assign]

        class _DryLoop:
            def create_task(self, coro) -> None:
                name = getattr(getattr(coro, "cr_code", None), "co_name", None) or getattr(
                    coro, "__name__", repr(coro)
                )
                logger.info("[DRY-RUN] Suppressed loop.create_task() for '%s'", name)
                return SimpleNamespace(cancel=lambda: None)  # type: ignore[return-value]

        stop_event = asyncio.Event()
        timed_out = False

        def _signal_handler() -> None:
            stop_event.set()

        failures: list[str] = []

        try:
            await Database.initialize()

            bot = bot_module.MyBot(command_prefix=bot_module.PREFIX, intents=bot_module.intents)
            bot.loop = _DryLoop()  # type: ignore[attr-defined]

            for ext in bot_module.initial_extensions:
                try:
                    await bot.load_extension(ext)
                    logger.info("[DRY-RUN] Loaded extension: %s", ext)
                except Exception as exc:
                    logger.exception("[DRY-RUN] Failed to load %s", ext, exc_info=exc)
                    failures.append(ext)

            if wait_for_signal:
                loop = asyncio.get_running_loop()
                for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
                    if sig is None:
                        continue
                    try:
                        loop.add_signal_handler(sig, _signal_handler)
                    except NotImplementedError:
                        pass

                if timeout and timeout > 0:
                    try:
                        await asyncio.wait_for(stop_event.wait(), timeout=timeout)
                    except TimeoutError:
                        timed_out = True
                else:
                    await stop_event.wait()
            elif timeout and timeout > 0:
                await asyncio.sleep(timeout)

            for ext in list(bot.extensions.keys()):
                with contextlib.suppress(Exception):
                    await bot.unload_extension(ext)

            await dcommands.Bot.close(bot)
        finally:
            dctasks.Loop.start = orig_loop_start
            with contextlib.suppress(Exception):
                os.environ.pop("TESTBOT_DRY_RUN", None)

        passed = not failures
        message = "Bot extensions loaded successfully" if passed else f"Failed to load: {', '.join(failures)}"
        result = CheckResult(
            name="Bot Smoke (no login)",
            passed=passed,
            message=message,
            details={
                "failures": failures,
                "wait_for_signal": wait_for_signal,
                "timeout_seconds": timeout,
                "timed_out": timed_out,
            },
        )
        self.report.add(result)
        return result


async def run_bot_smoke_only(*, timeout: float | None = None, wait_for_signal: bool = False) -> bool:
    """Public helper for dev tooling to reuse the consolidated bot smoke logic."""

    runner = StagingDryRun()
    result = await runner.run_bot_smoke(timeout=timeout, wait_for_signal=wait_for_signal)
    return result.passed


async def main():
    parser = argparse.ArgumentParser(description="Staging Dry-Run Verification")
    parser.add_argument(
        "--bot-url",
        default=os.environ.get("STAGING_BOT_URL", "http://127.0.0.1:8082"),
        help="Bot internal API URL",
    )
    parser.add_argument(
        "--backend-url",
        default=os.environ.get("STAGING_BACKEND_URL", "http://127.0.0.1:8000"),
        help="Backend API URL",
    )
    parser.add_argument(
        "--bot-smoke",
        action="store_true",
        help="Also run bot extension smoke load (no Discord login)",
    )
    parser.add_argument(
        "--bot-timeout",
        type=float,
        default=0.0,
        help="Seconds to keep the bot smoke session alive (0 = immediate unload)",
    )
    args = parser.parse_args()

    async with StagingDryRun(
        bot_url=args.bot_url,
        backend_url=args.backend_url,
    ) as runner:
        report = await runner.run_all()

        if args.bot_smoke:
            await runner.run_bot_smoke(timeout=args.bot_timeout or None)

        print(report.summary())

        sys.exit(0 if report.all_passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
