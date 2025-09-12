"""
Migration script to help transition from the old bot to the service-driven architecture.
"""

import asyncio
import json
from typing import Any

import yaml
from helpers.logger import get_logger
from services.db.database import Database

logger = get_logger(__name__)


async def migrate_config_to_guild_settings() -> None:
    """
    Migrate global config to per-guild settings in the database.
    
    This helps transition existing single-guild setups to multi-guild.
    """
    logger.info("Starting configuration migration")

    try:
        # Load existing config
        with open("config/config.yaml", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        # Initialize database
        await Database.initialize()

        # Get all guilds from the database (if any exist)
        async with Database.get_connection() as db:
            async with db.execute("SELECT DISTINCT guild_id FROM guild_registry") as cursor:
                guild_ids = [row[0] async for row in cursor]

        if not guild_ids:
            logger.warning("No guilds found in database. Skipping migration.")
            return

        # Migrate settings for each guild
        for guild_id in guild_ids:
            await migrate_guild_config(guild_id, config)

        logger.info(f"Configuration migration completed for {len(guild_ids)} guilds")

    except Exception as e:
        logger.exception(f"Error during configuration migration: {e}")
        raise


async def migrate_guild_config(guild_id: int, config: dict[str, Any]) -> None:
    """Migrate configuration for a specific guild."""
    logger.info(f"Migrating configuration for guild {guild_id}")

    async with Database.get_connection() as db:
        # Migrate role settings
        roles = config.get("roles", {})
        for role_key, role_value in roles.items():
            await db.execute("""
                INSERT OR REPLACE INTO guild_settings (guild_id, key, value)
                VALUES (?, ?, ?)
            """, (guild_id, f"roles.{role_key}", json.dumps(role_value)))

        # Migrate channel settings
        channels = config.get("channels", {})
        for channel_key, channel_value in channels.items():
            await db.execute("""
                INSERT OR REPLACE INTO guild_settings (guild_id, key, value)
                VALUES (?, ?, ?)
            """, (guild_id, f"channels.{channel_key}", json.dumps(channel_value)))

        # Migrate voice settings
        voice = config.get("voice", {})
        for voice_key, voice_value in voice.items():
            await db.execute("""
                INSERT OR REPLACE INTO guild_settings (guild_id, key, value)
                VALUES (?, ?, ?)
            """, (guild_id, f"voice.{voice_key}", json.dumps(voice_value)))

        # Migrate other settings
        other_keys = ["rate_limits", "organization", "logging", "bulk_announcement"]
        for key in other_keys:
            if key in config:
                value = config[key]
                await db.execute("""
                    INSERT OR REPLACE INTO guild_settings (guild_id, key, value)
                    VALUES (?, ?, ?)
                """, (guild_id, key, json.dumps(value)))

        await db.commit()

        logger.info(f"Configuration migrated for guild {guild_id}")


async def migrate_voice_tables() -> None:
    """
    Migrate old voice channel tables to new schema.
    """
    logger.info("Starting voice table migration")

    try:
        await Database.initialize()

        async with Database.get_connection() as db:
            # Check if old table exists
            async with db.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='user_voice_channels'
            """) as cursor:
                old_table_exists = bool(await cursor.fetchone())

            if not old_table_exists:
                logger.info("Old voice table does not exist. Skipping migration.")
                return

            # Create new voice_channels table if it doesn't exist
            await db.execute("""
                CREATE TABLE IF NOT EXISTS voice_channels (
                    guild_id INTEGER NOT NULL,
                    jtc_channel_id INTEGER NOT NULL,
                    owner_id INTEGER NOT NULL,
                    voice_channel_id INTEGER NOT NULL,
                    created_at INTEGER DEFAULT (strftime('%s','now')),
                    last_activity INTEGER DEFAULT (strftime('%s','now')),
                    is_active INTEGER DEFAULT 1,
                    PRIMARY KEY (guild_id, jtc_channel_id, owner_id)
                )
            """)

            # Migrate data from old table to new table
            await db.execute("""
                INSERT OR REPLACE INTO voice_channels 
                (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at, last_activity, is_active)
                SELECT 
                    guild_id, 
                    jtc_channel_id, 
                    owner_id, 
                    voice_channel_id, 
                    created_at,
                    created_at as last_activity,
                    1 as is_active
                FROM user_voice_channels
            """)

            await db.commit()

            # Count migrated records
            async with db.execute("SELECT COUNT(*) FROM voice_channels") as cursor:
                count = (await cursor.fetchone())[0]

            logger.info(f"Migrated {count} voice channel records")

            # Note: We don't drop the old table to be safe
            logger.info("Old table preserved for safety. You can drop 'user_voice_channels' manually if needed.")

    except Exception as e:
        logger.exception(f"Error during voice table migration: {e}")
        raise


async def create_sample_guild_config(guild_id: int) -> None:
    """
    Create a sample guild configuration for testing.
    
    Args:
        guild_id: Discord guild ID to create config for
    """
    logger.info(f"Creating sample configuration for guild {guild_id}")

    await Database.initialize()

    # Sample configuration
    sample_config = {
        "roles.bot_verified_role_id": 1313551309869416528,
        "roles.main_role_id": 1313551051076665394,
        "roles.affiliate_role_id": 1313551109373165671,
        "roles.non_member_role_id": 1313551221625192458,
        "roles.bot_admins": ["246604397155581954"],
        "roles.lead_moderators": ["1174838659065847859"],
        "channels.verification_channel_id": 1313551608491282543,
        "channels.bot_spam_channel_id": 1395475681512652999,
        "channels.public_announcement_channel_id": 1395475641805176952,
        "channels.leadership_announcement_channel_id": 1395475681512652944,
        "voice.cooldown_seconds": 5,
        "voice.expiry_days": 30,
        "voice.jtc_channels": [],  # Add your JTC channel IDs here
    }

    async with Database.get_connection() as db:
        for key, value in sample_config.items():
            await db.execute("""
                INSERT OR REPLACE INTO guild_settings (guild_id, key, value)
                VALUES (?, ?, ?)
            """, (guild_id, key, json.dumps(value)))

        await db.commit()

    logger.info(f"Sample configuration created for guild {guild_id}")


async def main() -> None:
    """Main migration function."""
    import argparse

    parser = argparse.ArgumentParser(description="Migration utilities for the refactored bot")
    parser.add_argument("--migrate-config", action="store_true", help="Migrate config to guild settings")
    parser.add_argument("--migrate-voice", action="store_true", help="Migrate voice tables")
    parser.add_argument("--sample-guild", type=int, help="Create sample config for guild ID")
    parser.add_argument("--all", action="store_true", help="Run all migrations")

    args = parser.parse_args()

    if args.all:
        await migrate_config_to_guild_settings()
        await migrate_voice_tables()
    else:
        if args.migrate_config:
            await migrate_config_to_guild_settings()

        if args.migrate_voice:
            await migrate_voice_tables()

        if args.sample_guild:
            await create_sample_guild_config(args.sample_guild)


if __name__ == "__main__":
    asyncio.run(main())
