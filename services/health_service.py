"""
Health service for monitoring bot health and providing status information.
"""

import asyncio
import time
from typing import Any

import discord
import psutil

from services.db.database import Database

from .base import BaseService


class HealthService(BaseService):
    """
    Service for monitoring and reporting bot health status.

    Provides health checks, performance metrics, and system information
    for monitoring and debugging purposes.
    """

    def __init__(self) -> None:
        super().__init__("health")
        self.start_time = time.monotonic()
        self._metrics: dict[str, Any] = {}
        self._metrics_lock = asyncio.Lock()

    async def _initialize_impl(self) -> None:
        """Initialize health service."""
        await self._reset_metrics()

    async def _reset_metrics(self) -> None:
        """Reset metrics to default values."""
        async with self._metrics_lock:
            self._metrics = {
                "commands_processed": 0,
                "events_processed": 0,
                "errors_encountered": 0,
                "voice_channels_created": 0,
                "verifications_completed": 0,
            }

    async def record_metric(self, metric_name: str, increment: int = 1) -> None:
        """
        Record a metric event.

        Args:
            metric_name: Name of the metric to increment
            increment: Amount to increment by (default 1)
        """
        async with self._metrics_lock:
            current = self._metrics.get(metric_name, 0)
            self._metrics[metric_name] = current + increment

    async def get_system_info(self) -> dict[str, Any]:
        """
        Get system information.

        Returns:
            Dict containing system metrics
        """
        process = psutil.Process()

        return {
            "cpu_percent": process.cpu_percent(),
            "memory_mb": process.memory_info().rss / 1024 / 1024,
            "memory_percent": process.memory_percent(),
            "open_files": len(process.open_files()),
            "threads": process.num_threads(),
            "uptime_seconds": time.monotonic() - self.start_time,
        }

    async def get_discord_info(self, bot: discord.Client) -> dict[str, Any]:
        """
        Get Discord-related information.

        Args:
            bot: Discord bot instance

        Returns:
            Dict containing Discord metrics
        """
        return {
            "guilds": len(bot.guilds),
            "users": len(bot.users),
            "latency_ms": round(bot.latency * 1000, 2),
            "is_ready": bot.is_ready(),
            "is_closed": bot.is_closed(),
        }

    async def get_database_info(self) -> dict[str, Any]:
        """
        Get database health information.

        Returns:
            Dict containing database metrics
        """
        try:
            async with Database.get_connection() as db:
                # Test basic connectivity
                await db.execute("SELECT 1")

                # Get table counts
                tables_info = {}
                table_names = [
                    "verification",
                    "guild_settings",
                    "user_voice_channels",
                    "voice_cooldowns",
                    "channel_settings",
                    "guild_registry"
                ]

                for table in table_names:
                    try:
                        async with db.execute(f"SELECT COUNT(*) FROM {table}") as cursor:
                            count = await cursor.fetchone()
                            tables_info[f"{table}_count"] = count[0] if count else 0
                    except Exception:
                        # Table might not exist
                        tables_info[f"{table}_count"] = "N/A"

                return {
                    "connected": True,
                    "tables": tables_info,
                }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e),
            }

    async def run_health_checks(
        self,
        bot: discord.Client,
        services: list[BaseService]
    ) -> dict[str, Any]:
        """
        Run comprehensive health checks.

        Args:
            bot: Discord bot instance
            services: List of services to check

        Returns:
            Dict containing complete health report
        """
        self._ensure_initialized()

        health_report = {
            "timestamp": time.time(),
            "overall_status": "healthy",
            "system": await self.get_system_info(),
            "discord": await self.get_discord_info(bot),
            "database": await self.get_database_info(),
            "services": {},
        }

        # Check all services
        service_statuses = []
        for service in services:
            try:
                service_health = await service.health_check()
                health_report["services"][service.name] = service_health
                service_statuses.append(service_health.get("status", "unknown"))
            except Exception as e:
                health_report["services"][service.name] = {
                    "status": "error",
                    "error": str(e)
                }
                service_statuses.append("error")

        # Add metrics
        async with self._metrics_lock:
            health_report["metrics"] = self._metrics.copy()

        # Determine overall status
        if not health_report["database"]["connected"]:
            health_report["overall_status"] = "unhealthy"
        elif "error" in service_statuses or not bot.is_ready():
            health_report["overall_status"] = "degraded"

        return health_report

    async def get_uptime_string(self) -> str:
        """
        Get formatted uptime string.

        Returns:
            Human readable uptime string
        """
        uptime_seconds = int(time.monotonic() - self.start_time)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"

    async def health_check(self) -> dict[str, Any]:
        """Return health information for the health service itself."""
        base_health = await super().health_check()

        async with self._metrics_lock:
            metrics_count = len(self._metrics)

        return {
            **base_health,
            "uptime_seconds": time.monotonic() - self.start_time,
            "metrics_tracked": metrics_count,
        }
