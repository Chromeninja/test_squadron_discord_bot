"""
Base service class providing common functionality for all services.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Any

from utils.logging import get_logger


class BaseService(ABC):
    """
    Abstract base class for all services in the bot.

    Provides common functionality like logging, initialization lifecycle,
    and error handling patterns.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.logger = get_logger(f"services.{name}")
        self._initialized = False
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize the service. Ensures single initialization."""
        async with self._lock:
            if self._initialized:
                return

            self.logger.info(f"Initializing {self.name} service")
            try:
                await self._initialize_impl()
                self._initialized = True
                self.logger.info(f"{self.name} service initialized successfully")
            except Exception as e:
                self.logger.exception(
                    "Failed to initialize %s service", self.name, exc_info=e
                )
                raise

    async def shutdown(self) -> None:
        """Shutdown the service and cleanup resources."""
        if not self._initialized:
            return

        self.logger.info(f"Shutting down {self.name} service")
        try:
            await self._shutdown_impl()
        except Exception as e:
            self.logger.exception(
                "Error during %s service shutdown", self.name, exc_info=e
            )
        finally:
            self._initialized = False

    @abstractmethod
    async def _initialize_impl(self) -> None:
        """Subclass-specific initialization logic."""
        pass

    async def _shutdown_impl(self) -> None:
        """Subclass-specific shutdown logic. Override if needed."""
        pass

    def _ensure_initialized(self) -> None:
        """Raise an error if the service is not initialized."""
        if not self._initialized:
            raise RuntimeError(f"{self.name} service is not initialized")

    async def health_check(self) -> dict[str, Any]:
        """
        Return health status of this service.

        Returns:
            Dict containing health information
        """
        return {
            "service": self.name,
            "initialized": self._initialized,
            "status": "healthy" if self._initialized else "not_initialized",
        }
