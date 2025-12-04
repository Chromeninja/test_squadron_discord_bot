#!/usr/bin/env python3
"""
Migration script: Copy lead_moderators to moderators role list.

This script migrates existing roles.lead_moderators values to roles.moderators
while preserving the original lead_moderators entries for backward compatibility
and rollback safety.

Usage:
    python scripts/migrate_lead_mods_to_moderators.py [--dry-run]

Options:
    --dry-run    Show what would be changed without making modifications
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.db.database import Database
from utils.logging import get_logger

logger = get_logger(__name__)


async def migrate_lead_mods_to_moderators(dry_run: bool = False) -> None:
    """Migrate lead_moderators to moderators for all guilds."""

    await Database.initialize()

    async with Database.get_connection() as db:
        # Find all guilds with lead_moderators configured
        cursor = await db.execute(
            """
            SELECT guild_id, value
            FROM guild_settings
            WHERE key = 'roles.lead_moderators'
            """
        )
        rows = list(await cursor.fetchall())

        if not rows:
            logger.info("No guilds found with lead_moderators configured")
            return

        logger.info(f"Found {len(rows)} guild(s) with lead_moderators")

        migrated_count = 0
        skipped_count = 0

        for guild_id, lead_mods_value in rows:
            # Check if moderators already exists
            check_cursor = await db.execute(
                """
                SELECT value
                FROM guild_settings
                WHERE guild_id = ? AND key = 'roles.moderators'
                """,
                (guild_id,)
            )
            existing = await check_cursor.fetchone()

            if existing:
                existing_value = existing[0]
                logger.info(
                    f"Guild {guild_id}: moderators already exists, skipping "
                    f"(current: {existing_value})"
                )
                skipped_count += 1
                continue

            # Parse lead_moderators value
            try:
                lead_mods_list = json.loads(lead_mods_value) if lead_mods_value else []
            except (json.JSONDecodeError, TypeError):
                logger.warning(
                    f"Guild {guild_id}: Invalid lead_moderators value, skipping: {lead_mods_value}"
                )
                skipped_count += 1
                continue

            if dry_run:
                logger.info(
                    f"[DRY RUN] Guild {guild_id}: Would copy {len(lead_mods_list)} "
                    f"lead_moderators to moderators: {lead_mods_list}"
                )
            else:
                # Copy lead_moderators to moderators
                await db.execute(
                    """
                    INSERT INTO guild_settings (guild_id, key, value)
                    VALUES (?, 'roles.moderators', ?)
                    """,
                    (guild_id, lead_mods_value)
                )

                logger.info(
                    f"Guild {guild_id}: Copied {len(lead_mods_list)} lead_moderators "
                    f"to moderators: {lead_mods_list}"
                )

            migrated_count += 1

        if not dry_run:
            await db.commit()
            logger.info(f"✅ Migration complete: {migrated_count} migrated, {skipped_count} skipped")
        else:
            logger.info(f"[DRY RUN] Would migrate: {migrated_count} guilds, skip: {skipped_count} guilds")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate lead_moderators to moderators role list"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without making modifications"
    )

    args = parser.parse_args()

    print("=" * 70)
    print("Lead Moderators → Moderators Migration")
    print("=" * 70)
    print()

    if args.dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")
    else:
        print("⚠️  LIVE MODE - Database will be modified")
        response = input("Continue? (yes/no): ").strip().lower()
        if response != "yes":
            print("Migration cancelled")
            return

    print()

    try:
        asyncio.run(migrate_lead_mods_to_moderators(dry_run=args.dry_run))
    except KeyboardInterrupt:
        print("\n\nMigration interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
