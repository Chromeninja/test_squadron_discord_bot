"""
Service Container

Central registry for all bot services providing dependency injection and service lifecycle management.
"""

from typing import TYPE_CHECKING, Optional

from utils.logging import get_logger

from .config_service import ConfigService
from .guild_config_helper import GuildConfigHelper
from .guild_service import GuildService
from .health_service import HealthService
from .role_delegation_service import RoleDelegationService
from .verification_bulk_service import VerificationBulkService
from .voice_service import VoiceService

if TYPE_CHECKING:
    from discord.ext.commands import Bot


class ServiceContainer:
    """
    Central container for managing all bot services.

    Provides a centralized access point for services throughout the bot,
    handles initialization order, and manages service dependencies.
    """

    def __init__(self, bot: Optional["Bot"] = None) -> None:
        self.logger = get_logger("services.container")
        self.bot = bot  # Store bot instance for services that need it
        self._config: ConfigService | None = None
        self._guild_config: GuildConfigHelper | None = None
        self._guild: GuildService | None = None
        self._voice: VoiceService | None = None
        self._health: HealthService | None = None
        self._role_delegation: RoleDelegationService | None = None
        self._verify_bulk: VerificationBulkService | None = None
        self._initialized = False

    @property
    def config(self) -> ConfigService:
        """Get the configuration service."""
        if self._config is None:
            raise RuntimeError("ConfigService not initialized")
        return self._config

    @property
    def guild_config(self) -> GuildConfigHelper:
        """Get the guild configuration helper."""
        if self._guild_config is None:
            raise RuntimeError("GuildConfigHelper not initialized")
        return self._guild_config

    @property
    def guild(self) -> GuildService:
        """Get the guild service."""
        if self._guild is None:
            raise RuntimeError("GuildService not initialized")
        return self._guild

    @property
    def voice(self) -> VoiceService:
        """Get the voice service."""
        if self._voice is None:
            raise RuntimeError("VoiceService not initialized")
        return self._voice

    @property
    def health(self) -> HealthService:
        """Get the health service."""
        if self._health is None:
            raise RuntimeError("HealthService not initialized")
        return self._health

    @property
    def role_delegation(self) -> RoleDelegationService:
        """Get the role delegation service."""
        if self._role_delegation is None:
            raise RuntimeError("RoleDelegationService not initialized")
        return self._role_delegation

    @property
    def verify_bulk(self) -> VerificationBulkService:
        """Get the verification bulk service."""
        if self._verify_bulk is None:
            raise RuntimeError("VerificationBulkService not initialized")
        return self._verify_bulk

    def get_all_services(self) -> list:
        """Get all initialized services for health monitoring."""
        services = []
        if self._config:
            services.append(self._config)
        # guild_config is a helper, not a service with lifecycle
        if self._guild:
            services.append(self._guild)
        if self._voice:
            services.append(self._voice)
        if self._health:
            services.append(self._health)
        if self._role_delegation:
            services.append(self._role_delegation)
        if self._verify_bulk:
            services.append(self._verify_bulk)
        return services

    async def initialize(self) -> None:
        """Initialize all services in dependency order."""
        if self._initialized:
            self.logger.warning("ServiceContainer already initialized")
            return

        try:
            self.logger.info("Initializing services")

            # Initialize config service first (no dependencies)
            self._config = ConfigService()
            await self._config.initialize()
            self.logger.debug("ConfigService initialized")

            # Initialize guild config helper (depends on config and bot)
            if not self.bot:
                raise RuntimeError("Bot instance required for GuildConfigHelper")
            self._guild_config = GuildConfigHelper(self.bot, self._config)
            self.logger.debug("GuildConfigHelper initialized")

            # Initialize guild service (depends on config)
            self._guild = GuildService(self._config)
            await self._guild.initialize()
            self.logger.debug("GuildService initialized")

            # Initialize voice service (depends on config and bot)
            self._voice = VoiceService(self._config, self.bot)
            await self._voice.initialize()
            self.logger.debug("VoiceService initialized")

            # Initialize role delegation service (depends on config and bot)
            self._role_delegation = RoleDelegationService(self._config, self.bot)
            await self._role_delegation.initialize()
            self.logger.debug("RoleDelegationService initialized")

            # Initialize health service (no dependencies)
            self._health = HealthService()
            await self._health.initialize()
            self.logger.debug("HealthService initialized")

            # Initialize verification bulk service (depends on bot and config)
            if self.bot:
                self._verify_bulk = VerificationBulkService(self.bot)  # type: ignore[arg-type]
                await self._verify_bulk.start()
                self.logger.debug("VerificationBulkService initialized")

            self._initialized = True
            self.logger.info("All services initialized successfully")

        except Exception as e:
            self.logger.exception("Failed to initialize services", exc_info=e)
            raise

    async def cleanup(self) -> None:
        """Clean up all services in reverse dependency order."""
        if not self._initialized:
            return

        self.logger.info("Cleaning up services")

        # Cleanup in reverse order
        if self._verify_bulk:
            await self._verify_bulk.shutdown()
            self._verify_bulk = None

        if self._health:
            await self._health.shutdown()
            self._health = None

        if self._voice:
            await self._voice.shutdown()
            self._voice = None

        if self._role_delegation:
            await self._role_delegation.shutdown()
            self._role_delegation = None

        if self._guild:
            await self._guild.shutdown()
            self._guild = None

        if self._config:
            await self._config.shutdown()
            self._config = None

        # guild_config has no cleanup needed (it's just a helper)
        self._guild_config = None

        self._initialized = False
        self.logger.info("Services cleaned up")
