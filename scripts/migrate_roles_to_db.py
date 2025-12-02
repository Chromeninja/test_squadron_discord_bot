#!/usr/bin/env python3
"""
Migration script to move role configuration from config.yaml to database.

Usage:
    python scripts/migrate_roles_to_db.py --guild-id 246486575137947648
    python scripts/migrate_roles_to_db.py --guild-id 123456789 --config path/to/config.yaml
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import yaml

from services.db.database import Database


async def migrate_roles(guild_id: int, config_path: str, dry_run: bool = False):
    """Migrate roles from config.yaml to database."""

    print(f"🔍 Reading configuration from: {config_path}")

    # Load config file
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"❌ Error: Config file not found at {config_path}")
        return False
    except yaml.YAMLError as e:
        print(f"❌ Error parsing YAML: {e}")
        return False

    # Extract roles section
    roles = config.get("roles", {})
    if not roles:
        print("⚠️  No roles section found in config.yaml")
        print("    If you've already migrated, you're all set!")
        return True

    print("\n📋 Found role configuration:")
    print(f"   Bot Admins: {roles.get('bot_admins', [])}")
    print(f"   Lead Moderators: {roles.get('lead_moderators', [])}")
    print(f"   Main Role: {roles.get('main_role', [])}")
    print(f"   Affiliate Role: {roles.get('affiliate_role', [])}")
    print(f"   Non-Member Role: {roles.get('nonmember_role', [])}")

    # Prepare database inserts
    migrations = []

    if roles.get("bot_admins"):
        migrations.append(("roles.bot_admins", json.dumps(roles["bot_admins"])))

    if roles.get("lead_moderators"):
        migrations.append(
            ("roles.lead_moderators", json.dumps(roles["lead_moderators"]))
        )

    if roles.get("main_role"):
        # Convert single role to list format for consistency
        main_roles = (
            roles["main_role"]
            if isinstance(roles["main_role"], list)
            else [roles["main_role"]]
        )
        migrations.append(("roles.main_role", json.dumps(main_roles)))

    if roles.get("affiliate_role"):
        affiliate_roles = (
            roles["affiliate_role"]
            if isinstance(roles["affiliate_role"], list)
            else [roles["affiliate_role"]]
        )
        migrations.append(("roles.affiliate_role", json.dumps(affiliate_roles)))

    if roles.get("nonmember_role"):
        nonmember_roles = (
            roles["nonmember_role"]
            if isinstance(roles["nonmember_role"], list)
            else [roles["nonmember_role"]]
        )
        migrations.append(("roles.nonmember_role", json.dumps(nonmember_roles)))

    if not migrations:
        print("\n⚠️  No role data to migrate")
        return True

    print(
        f"\n{'🔍 DRY RUN MODE - No changes will be made' if dry_run else '💾 Migrating to database...'}"
    )
    print(f"   Target Guild ID: {guild_id}")

    if dry_run:
        print("\n📝 SQL statements that would be executed:")
        for key, value in migrations:
            print("   INSERT OR REPLACE INTO guild_settings (guild_id, key, value)")
            print(f"   VALUES ({guild_id}, '{key}', '{value}');")
        print("\n✅ Dry run complete. Run without --dry-run to apply changes.")
        return True

    # Initialize database
    db_path = config.get("database", {}).get("path", "TESTDatabase.db")
    if not Path(db_path).is_absolute():
        db_path = str(project_root / db_path)

    print(f"   Database: {db_path}")

    await Database.initialize(db_path)

    # Insert into database
    async with Database.get_connection() as db:
        for key, value in migrations:
            await db.execute(
                "INSERT OR REPLACE INTO guild_settings (guild_id, key, value) VALUES (?, ?, ?)",
                (guild_id, key, value),
            )
        await db.commit()

    print("\n✅ Migration complete!")
    print("\n📋 Next steps:")
    print("   1. Verify roles in web dashboard or by querying database:")
    print(
        f'      sqlite3 {db_path} "SELECT * FROM guild_settings WHERE guild_id = {guild_id};"'
    )
    print("   2. Test bot admin commands to ensure permissions work")
    print("   3. Once verified, remove the 'roles:' section from config.yaml")

    return True


async def main():
    parser = argparse.ArgumentParser(
        description="Migrate role configuration from config.yaml to database"
    )
    parser.add_argument(
        "--guild-id",
        type=int,
        required=True,
        help="Discord guild ID to migrate roles for",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/config.yaml",
        help="Path to config.yaml (default: config/config.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without making changes",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("🔧 Role Configuration Migration Tool")
    print("=" * 60)

    success = await migrate_roles(args.guild_id, args.config, args.dry_run)

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
