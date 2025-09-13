"""
Service manager for coordinating all bot services.
"""

from typing import Any

from utils.logging import get_logger

from .base import BaseService
from .config_service import ConfigService
from .guild_service import GuildService
from .health_service import HealthService
from .voice_service import VoiceService


class ServiceManager:
    """
    Manages the lifecycle and coordination of all bot services.

    Provides a central point for initializing, accessing, and shutting down
    all services in the correct order.
    """

    def __init__(self) -> None:
        self.logger = get_logger("services.manager")
        self._services: dict[str, BaseService] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize all services in the correct dependency order."""
        if self._initialized:
            return

        self.logger.info("Initializing services")

        try:
            # Initialize services in dependency order
            self.config = ConfigService()
            await self.config.initialize()
            self._services["config"] = self.config

            self.guild = GuildService(self.config)
            await self.guild.initialize()
            self._services["guild"] = self.guild

            self.health = HealthService()
            await self.health.initialize()
            self._services["health"] = self.health

            self.voice = VoiceService(self.config)
            await self.voice.initialize()
            self._services["voice"] = self.voice

            self._initialized = True
            self.logger.info("All services initialized successfully")

        except Exception as e:
            self.logger.exception(f"Failed to initialize services: {e}")
            await self.shutdown()
            raise

    async def shutdown(self) -> None:
        """Shutdown all services in reverse order."""
        if not self._initialized:
            return

        self.logger.info("Shutting down services")

        # Shutdown in reverse order
        for service_name in reversed(list(self._services.keys())):
            service = self._services[service_name]
            try:
                await service.shutdown()
                self.logger.debug(f"Service {service_name} shutdown complete")
            except Exception as e:
                self.logger.exception(f"Error shutting down service {service_name}: {e}")

        self._services.clear()
        self._initialized = False
        self.logger.info("Service shutdown complete")

    def get_service(self, service_name: str) -> BaseService:
        """
        Get a service by name.

        Args:
            service_name: Name of the service to retrieve

        Returns:
            The requested service

        Raises:
            KeyError: If service is not found
            RuntimeError: If services are not initialized
        """
        if not self._initialized:
            raise RuntimeError("Services are not initialized")

        if service_name not in self._services:
            raise KeyError(f"Service '{service_name}' not found")

        return self._services[service_name]

    def get_all_services(self) -> list[BaseService]:
        """
        Get all services.

        Returns:
            List of all registered services
        """
        return list(self._services.values())

    async def health_check_all(self) -> dict[str, Any]:
        """
        Run health checks on all services.

        Returns:
            Dict containing health status of all services
        """
        if not self._initialized:
            return {"status": "not_initialized", "services": {}}

        health_results = {}
        overall_healthy = True

        for service_name, service in self._services.items():
            try:
                health_results[service_name] = await service.health_check()
                if health_results[service_name].get("status") != "healthy":
                    overall_healthy = False
            except Exception as e:
                health_results[service_name] = {
                    "status": "error",
                    "error": str(e)
                }
                overall_healthy = False

        return {
            "status": "healthy" if overall_healthy else "degraded",
            "services": health_results
        }

    @property
    def is_initialized(self) -> bool:
        """Check if services are initialized."""
        return self._initialized
