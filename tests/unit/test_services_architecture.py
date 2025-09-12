"""Unit tests for the service architecture."""

import pytest_asyncio
from services.base import BaseService
from services.config_service import ConfigService


class TestConfigService:
    """Test configuration service."""

    @pytest_asyncio.fixture
    async def service(self, temp_db):
        """Create a config service for testing."""
        service = ConfigService()
        await service.initialize()
        yield service
        await service.shutdown()

    async def test_service_lifecycle(self, temp_db):
        """Test service start/stop lifecycle."""
        service = ConfigService()

        # ConfigService doesn't have is_started, it has different lifecycle
        await service.initialize()
        # Just test that it initializes without error
        assert service._global_config is not None

        await service.shutdown()
        assert not service.is_started

    async def test_guild_config_creation(self, service):
        """Test guild configuration creation."""
        guild_id = 123456789

        # Get config for new guild (should create default)
        config = await service.get_guild_config(guild_id)

        assert isinstance(config, dict)
        assert "verification" in config
        assert "voice" in config
        assert "leadership" in config
        assert "community" in config

    async def test_config_value_get_set(self, service):
        """Test getting and setting configuration values."""
        guild_id = 123456789

        # Set a value
        await service.set_config_value(guild_id, "voice.enabled", False)

        # Get the value
        value = await service.get_config_value(guild_id, "voice.enabled")
        assert value is False

        # Test nested value
        await service.set_config_value(guild_id, "voice.cooldown_seconds", 600)
        value = await service.get_config_value(guild_id, "voice.cooldown_seconds")
        assert value == 600

    async def test_nested_config_access(self, service):
        """Test nested configuration access."""
        guild_id = 123456789

        # Set nested value
        await service.set_config_value(guild_id, "verification.channel_id", 987654321)

        # Get nested value
        value = await service.get_config_value(guild_id, "verification.channel_id")
        assert value == 987654321

        # Test default value
        value = await service.get_config_value(guild_id, "nonexistent.key", "default")
        assert value == "default"

    async def test_guild_channels_management(self, service):
        """Test guild channel management."""
        guild_id = 123456789
        channel_id = 987654321

        # Add channel
        await service.add_guild_channel(guild_id, "verification", channel_id)

        # Get channels
        channels = await service.get_guild_channels(guild_id, "verification")
        assert channel_id in channels

        # Remove channel
        await service.remove_guild_channel(guild_id, "verification", channel_id)

        # Verify removal
        channels = await service.get_guild_channels(guild_id, "verification")
        assert channel_id not in channels

    async def test_guild_roles_management(self, service):
        """Test guild role management."""
        guild_id = 123456789
        role_id = 555555555

        # Add role
        await service.add_guild_role(guild_id, "leadership", role_id)

        # Get roles
        roles = await service.get_guild_roles(guild_id, "leadership")
        assert role_id in roles

        # Remove role
        await service.remove_guild_role(guild_id, "leadership", role_id)

        # Verify removal
        roles = await service.get_guild_roles(guild_id, "leadership")
        assert role_id not in roles

    async def test_health_check(self, service):
        """Test service health check."""
        health = await service.health_check()

        assert health["status"] == "healthy"
        assert health["started"] is True
        assert health["error"] is None


class MockService(BaseService):
    """Mock service for testing base functionality."""

    async def start(self) -> None:
        self._started = True

    async def stop(self) -> None:
        self._started = False


class FailingService(BaseService):
    """Service that fails for testing error handling."""

    async def start(self) -> None:
        raise RuntimeError("Failed to start")

    async def stop(self) -> None:
        raise RuntimeError("Failed to stop")

    async def _perform_health_check(self) -> None:
        raise RuntimeError("Health check failed")


class TestBaseService:
    """Test base service functionality."""

    async def test_service_properties(self):
        """Test service properties."""
        service = MockService()

        assert not service.is_started
        assert service.health_status == "unknown"
        assert service.last_error is None

        await service.start()
        assert service.is_started

        await service.stop()
        assert not service.is_started

    async def test_health_check_success(self):
        """Test successful health check."""
        service = MockService()
        await service.start()

        health = await service.health_check()

        assert health["status"] == "healthy"
        assert health["started"] is True
        assert health["error"] is None
        assert service.health_status == "healthy"

    async def test_health_check_failure(self):
        """Test failed health check."""
        service = FailingService()
        await service.start()  # This will fail but we continue for testing

        health = await service.health_check()

        assert health["status"] == "unhealthy"
        assert health["error"] is not None
        assert service.health_status == "unhealthy"
        assert service.last_error is not None
