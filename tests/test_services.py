"""
Tests for the service architecture.
"""

import contextlib
import tempfile
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

from services import (
    ConfigService,
    GuildService,
    HealthService,
    VoiceService,
)
from services.db.database import Database
from services.service_container import ServiceContainer


@pytest_asyncio.fixture
async def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    await Database.initialize(db_path)
    yield db_path

    # Cleanup
    from pathlib import Path

    with contextlib.suppress(OSError):
        Path(db_path).unlink()


@pytest.fixture
async def service_container(temp_db):
    """Create a service container with temporary database."""
    container = ServiceContainer()
    await container.initialize()
    yield container
    await container.cleanup()


class TestConfigService:
    """Tests for ConfigService."""

    @pytest.mark.asyncio
    async def test_config_service_initialization(self, temp_db):
        """Test config service initializes correctly."""
        config_service = ConfigService()
        await config_service.initialize()

        assert config_service._initialized
        await config_service.shutdown()

    @pytest.mark.asyncio
    async def test_guild_setting_storage(self, temp_db):
        """Test storing and retrieving guild settings."""
        # Force reinitialization with the test database
        Database._initialized = False
        Database._db_path = temp_db
        await Database.initialize(temp_db)

        config_service = ConfigService()
        await config_service.initialize()

        guild_id = 12345
        key = "test.setting"
        value = {"nested": "value"}

        # Set setting
        await config_service.set_guild_setting(guild_id, key, value)

        # Get setting
        retrieved = await config_service.get_guild_setting(guild_id, key)
        print(f"DEBUG: Set {value}, got back: {retrieved}")
        assert retrieved == value

        await config_service.shutdown()

    @pytest.mark.asyncio
    async def test_nested_key_access(self, temp_db):
        """Test accessing nested configuration keys."""
        config_service = ConfigService()
        await config_service.initialize()

        # Set global config after initialization (since initialization loads from file)
        config_service._global_config = {"roles": {"admin": 123456}}

        # Test nested key access
        value = await config_service.get_global_setting("roles.admin")
        assert value == 123456

        # Test non-existent key
        value = await config_service.get_global_setting("roles.nonexistent", "default")
        assert value == "default"

        await config_service.shutdown()


class TestGuildService:
    """Tests for GuildService."""

    @pytest.mark.asyncio
    async def test_guild_service_initialization(self, temp_db):
        """Test guild service initializes correctly."""
        config_service = ConfigService()
        await config_service.initialize()

        guild_service = GuildService(config_service)
        await guild_service.initialize()

        assert guild_service._initialized

        await guild_service.shutdown()
        await config_service.shutdown()

    @pytest.mark.asyncio
    async def test_guild_registration(self, temp_db):
        """Test registering a guild."""
        # Force reinitialization with the test database
        Database._initialized = False
        Database._db_path = temp_db
        await Database.initialize(temp_db)

        config_service = ConfigService()
        await config_service.initialize()

        guild_service = GuildService(config_service)
        await guild_service.initialize()

        # Create mock guild
        guild = MagicMock()
        guild.id = 12345
        guild.name = "Test Guild"
        guild.roles = []

        # Register guild (just test that it doesn't crash)
        await guild_service.register_guild(guild)

        # Guild registration successful if no exception raised
        assert True

        await guild_service.shutdown()
        await config_service.shutdown()


class TestHealthService:
    """Tests for HealthService."""

    @pytest.mark.asyncio
    async def test_health_service_initialization(self, temp_db):
        """Test health service initializes correctly."""
        health_service = HealthService()
        await health_service.initialize()

        assert health_service._initialized
        await health_service.shutdown()

    @pytest.mark.asyncio
    async def test_metric_recording(self, temp_db):
        """Test metric recording functionality."""
        health_service = HealthService()
        await health_service.initialize()

        # Record some metrics
        await health_service.record_metric("test_metric", 5)
        await health_service.record_metric("test_metric", 3)

        # Check metrics are recorded
        async with health_service._metrics_lock:
            assert health_service._metrics["test_metric"] == 8

        await health_service.shutdown()

    @pytest.mark.asyncio
    async def test_system_info(self, temp_db):
        """Test system information gathering."""
        health_service = HealthService()
        await health_service.initialize()

        system_info = await health_service.get_system_info()

        # Check required fields are present
        required_fields = [
            "cpu_percent",
            "memory_mb",
            "memory_percent",
            "threads",
            "uptime_seconds",
        ]
        for field in required_fields:
            assert field in system_info
            assert isinstance(system_info[field], int | float)

        await health_service.shutdown()


class TestVoiceService:
    """Tests for VoiceService."""

    @pytest.mark.asyncio
    async def test_voice_service_initialization(self, temp_db):
        """Test voice service initializes correctly."""
        config_service = ConfigService()
        await config_service.initialize()

        voice_service = VoiceService(config_service)
        await voice_service.initialize()

        assert voice_service._initialized

        await voice_service.shutdown()
        await config_service.shutdown()

    @pytest.mark.asyncio
    async def test_can_create_voice_channel(self, temp_db):
        """Test voice channel creation validation."""
        # Force reinitialization with the test database
        Database._initialized = False
        Database._db_path = temp_db
        await Database.initialize(temp_db)

        config_service = ConfigService()
        await config_service.initialize()

        voice_service = VoiceService(config_service)
        await voice_service.initialize()

        guild_id = 12345
        jtc_channel_id = 67890
        user_id = 111

        # Test creation when allowed
        can_create, _reason = await voice_service.can_create_voice_channel(
            guild_id, jtc_channel_id, user_id
        )

        # Should be able to create since no existing channel
        assert can_create is True

        await voice_service.shutdown()
        await config_service.shutdown()


class TestServiceContainer:
    """Tests for ServiceContainer."""

    @pytest.mark.asyncio
    async def test_service_container_initialization(self, temp_db):
        """Test service container initializes all services."""
        # Create a mock bot instance
        from unittest.mock import Mock
        mock_bot = Mock()
        mock_bot.get_channel = Mock(return_value=None)
        mock_bot.get_guild = Mock(return_value=None)

        container = ServiceContainer(bot=mock_bot)
        await container.initialize()

        assert container._initialized

        # Check all services are available
        assert container.config is not None
        assert container.guild_config is not None
        assert container.guild is not None
        assert container.health is not None
        assert container.voice is not None

        await container.cleanup()

    @pytest.mark.asyncio
    async def test_service_access(self, temp_db):
        """Test accessing services through container."""
        # Create a mock bot instance
        from unittest.mock import Mock
        mock_bot = Mock()
        mock_bot.get_channel = Mock(return_value=None)
        mock_bot.get_guild = Mock(return_value=None)

        container = ServiceContainer(bot=mock_bot)
        await container.initialize()

        # Test getting services
        assert isinstance(container.config, ConfigService)
        assert isinstance(container.guild, GuildService)

        await container.cleanup()

    @pytest.mark.asyncio
    async def test_health_check(self, temp_db):
        """Test health checking through services."""
        # Create a mock bot instance
        from unittest.mock import Mock
        mock_bot = Mock()
        mock_bot.get_channel = Mock(return_value=None)
        mock_bot.get_guild = Mock(return_value=None)

        container = ServiceContainer(bot=mock_bot)
        await container.initialize()

        # Check health service is available
        assert container.health is not None
        health_status = await container.health.health_check()
        assert health_status["status"] == "healthy"

        await container.cleanup()


@pytest.mark.asyncio
async def test_integration_flow(temp_db):
    """Test complete service integration flow."""
    # Force reinitialization with the test database
    Database._initialized = False
    Database._db_path = temp_db
    await Database.initialize(temp_db)

    # Create a mock bot instance
    from unittest.mock import Mock
    mock_bot = Mock()
    mock_bot.get_channel = Mock(return_value=None)
    mock_bot.get_guild = Mock(return_value=None)

    container = ServiceContainer(bot=mock_bot)
    await container.initialize()

    guild_id = 12345

    # Test configuration
    await container.config.set_guild_setting(guild_id, "voice.cooldown_seconds", 10)
    cooldown = await container.config.get_guild_setting(
        guild_id, "voice.cooldown_seconds"
    )
    assert cooldown == 10

    # Test health checks (using base health_check method)
    health_status = await container.health.health_check()
    assert health_status["status"] == "healthy"

    # Test service access
    assert container.config is not None
    assert container.guild is not None
    assert container.health is not None
    assert container.voice is not None

    await container.cleanup()


if __name__ == "__main__":
    pytest.main([__file__])
