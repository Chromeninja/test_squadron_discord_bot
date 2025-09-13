"""
Services Container

Provides a lightweight container for managing bot services with dependency injection.
"""

from utils.logging import get_logger

from .guild_config_service import GuildConfigService

logger = get_logger(__name__)


class Services:
    """
    Lightweight services container for the Discord bot.

    Holds named services and provides a clean interface for dependency injection.
    Framework-agnostic and async-ready.
    """

    def __init__(self) -> None:
        self.config: GuildConfigService | None = None
        self._initialized = False

    def initialize(self, *, ttl_seconds: int = 60) -> None:
        """
        Initialize all services.

        Args:
            ttl_seconds: Cache TTL for the guild config service
        """
        if self._initialized:
            logger.warning("Services already initialized")
            return

        # Initialize GuildConfigService
        self.config = GuildConfigService(ttl_seconds=ttl_seconds)

        self._initialized = True
        logger.info("Services container initialized")

    def ensure_initialized(self) -> None:
        """Ensure services are initialized, raising an error if not."""
        if not self._initialized:
            raise RuntimeError("Services not initialized. Call initialize() first.")

    @property
    def is_initialized(self) -> bool:
        """Check if services are initialized."""
        return self._initialized
