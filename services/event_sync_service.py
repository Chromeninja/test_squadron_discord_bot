"""Background service for periodic Discord scheduled-event pulls into the DB."""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any

from services.base import BaseService
from services.config_service import CONFIG_EVENTS_ENABLED, ConfigService
from web.backend.core.dependencies import InternalAPIClient
from web.backend.core.event_service import EventService

if TYPE_CHECKING:
    from discord.ext.commands import Bot


class EventSyncService(BaseService):
    """Runs periodic Discord-to-DB event reconciliation for all enabled guilds."""

    def __init__(
        self,
        config_service: ConfigService,
        bot: Bot,
        internal_api_client: InternalAPIClient | None = None,
    ) -> None:
        super().__init__("event_sync")
        self.config_service = config_service
        self.bot = bot
        self.internal_api_client = internal_api_client or InternalAPIClient()
        self._owns_internal_api_client = internal_api_client is None
        self._loop_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._run_lock = asyncio.Lock()
        self._enabled = True
        self._interval_seconds = 3600.0
        self._per_guild_delay_seconds = 2.0
        self._startup_delay_seconds = 60.0

    async def _initialize_impl(self) -> None:
        """Load config and start the background loop when enabled."""
        self._enabled = bool(
            await self.config_service.get_global_setting("events.sync.enabled", True)
        )
        interval_minutes = float(
            await self.config_service.get_global_setting(
                "events.sync.interval_minutes", 60
            )
        )
        self._interval_seconds = max(60.0, interval_minutes * 60.0)
        self._per_guild_delay_seconds = max(
            0.0,
            float(
                await self.config_service.get_global_setting(
                    "events.sync.per_guild_delay_seconds", 2.0
                )
            ),
        )
        self._startup_delay_seconds = max(
            0.0,
            float(
                await self.config_service.get_global_setting(
                    "events.sync.startup_delay_seconds", 60.0
                )
            ),
        )

        if not self._enabled:
            self.logger.info("Event sync background loop disabled by configuration")
            return

        self._stop_event.clear()
        self._loop_task = asyncio.create_task(
            self._worker_loop(), name="event_sync.loop"
        )

    async def _shutdown_impl(self) -> None:
        """Stop the background loop and close owned resources."""
        self._stop_event.set()
        if self._loop_task is not None:
            self._loop_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._loop_task
            self._loop_task = None

        if self._owns_internal_api_client:
            await self.internal_api_client.close()

    async def _worker_loop(self) -> None:
        """Run periodic pull-sync passes until shutdown."""
        try:
            if self._startup_delay_seconds > 0:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self._startup_delay_seconds
                )
                return
        except asyncio.TimeoutError:
            pass

        while not self._stop_event.is_set():
            try:
                await self.reconcile_all_guilds()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.logger.exception(
                    "Event sync pass failed", exc_info=exc
                )

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self._interval_seconds
                )
            except asyncio.TimeoutError:
                continue

    async def reconcile_all_guilds(self) -> None:
        """Pull scheduled events from Discord into DB for enabled guilds."""
        async with self._run_lock:
            for index, guild in enumerate(self.bot.guilds):
                if not await self.config_service.get_guild_setting(
                    guild.id,
                    CONFIG_EVENTS_ENABLED,
                    True,
                ):
                    continue

                result, _events = await EventService.manual_sync(
                    guild_id=guild.id,
                    direction="pull",
                    projection_client=self.internal_api_client,
                )
                self.logger.info(
                    "Event sync pull complete for guild %s: processed=%s updated=%s",
                    guild.id,
                    result.processed,
                    result.updated,
                )

                is_last_guild = index >= len(self.bot.guilds) - 1
                if not is_last_guild and self._per_guild_delay_seconds > 0:
                    await asyncio.sleep(self._per_guild_delay_seconds)

    async def health_check(self) -> dict[str, Any]:
        """Return health information for the background event sync loop."""
        return {
            "service": self.name,
            "initialized": self._initialized,
            "enabled": self._enabled,
            "status": "healthy"
            if self._initialized and (not self._enabled or self._loop_task is not None)
            else "not_initialized",
            "interval_seconds": self._interval_seconds,
            "per_guild_delay_seconds": self._per_guild_delay_seconds,
            "has_loop_task": self._loop_task is not None,
        }
