#!/usr/bin/env python3
"""
Create a comprehensive refactored bot with service architecture.
"""

import asyncio
import sys
import tempfile

import pytest

from services.db.database import Database
from services.service_manager import ServiceManager


@pytest.mark.asyncio
async def test_comprehensive_bot():
    """Test the complete bot with service architecture."""
    print("🚀 Testing Comprehensive Bot Refactoring")
    print("=" * 50)

    # Create temporary database for testing
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        test_db_path = f.name

    print(f"📂 Using test database: {test_db_path}")

    try:
        # Initialize database
        await Database.initialize(test_db_path)
        print("✅ Database initialized")

        # Initialize service manager
        manager = ServiceManager()
        await manager.initialize()
        print("✅ Service manager initialized")

        # Test guild configuration
        guild_id = 123456789
        print(f"\n🏰 Testing guild {guild_id} configuration...")

        # Set some guild-specific settings
        await manager.config.set_guild_setting(guild_id, "voice.cooldown_seconds", 15)
        await manager.config.set_guild_setting(guild_id, "roles.admin", 987654321)
        await manager.config.set_guild_setting(guild_id, "moderation.auto_kick", True)

        # Retrieve settings
        cooldown = await manager.config.get_guild_setting(
            guild_id, "voice.cooldown_seconds"
        )
        admin_role = await manager.config.get_guild_setting(guild_id, "roles.admin")
        auto_kick = await manager.config.get_guild_setting(
            guild_id, "moderation.auto_kick"
        )

        print(f"  ⚙️  Voice cooldown: {cooldown} seconds")
        print(f"  👑 Admin role ID: {admin_role}")
        print(f"  🚫 Auto kick enabled: {auto_kick}")

        # Test voice service
        print("\n🎤 Testing voice service...")
        can_create, reason = await manager.voice.can_create_voice_channel(
            guild_id, 555666777, 111222333
        )
        print(f"  ✅ Can create voice channel: {can_create} ({reason})")

        # Test health metrics
        print("\n💚 Testing health service...")
        await manager.health.record_metric("test_operations", 42)
        await manager.health.record_metric("api_calls", 128)

        # Get system info instead
        system_info = await manager.health.get_system_info()
        print(f"  💻 CPU usage: {system_info.get('cpu_percent', 'N/A')}%")
        print(f"  🧠 Memory usage: {system_info.get('memory_percent', 'N/A')}%")

        # Get health check for the service itself
        health_check = await manager.health.health_check()
        print(
            f"  ⏱️  Service uptime: {health_check.get('uptime_seconds', 0):.1f} seconds"
        )
        print(f"  � Metrics tracked: {health_check.get('metrics_tracked', 0)}")

        # Test service health check
        print("\n🔍 Testing service health checks...")
        all_health = await manager.health_check_all()
        print(f"  🌐 Overall status: {all_health['status']}")
        print(f"  📋 Raw health data: {all_health}")

        for service_name, service_health in all_health.get("services", {}).items():
            print(f"  🔧 {service_name}: {service_health}")

        # Shutdown services
        print("\n🛑 Shutting down services...")
        await manager.shutdown()
        print("✅ Clean shutdown completed")

        print("\n🎉 All tests completed successfully!")
        print("=" * 50)

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False

    finally:
        # Cleanup
        from pathlib import Path

        try:
            Path(test_db_path).unlink()
            print("🧹 Cleaned up test database")
        except OSError:
            pass


if __name__ == "__main__":
    success = asyncio.run(test_comprehensive_bot())
    sys.exit(0 if success else 1)
