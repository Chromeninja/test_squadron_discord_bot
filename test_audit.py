#!/usr/bin/env python3
"""
Test script for admin audit logging functionality.
Run this to verify the audit system is working correctly.
"""
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from helpers.audit import log_admin_action
from services.db.database import Database


async def test_audit_logging():
    """Test the audit logging functionality."""
    print("🧪 Testing Admin Audit Logging System\n")
    
    # Initialize database
    await Database.initialize("TESTDatabase.db")
    print("✅ Database initialized\n")
    
    # Test 1: Log a user recheck action
    print("Test 1: Logging RECHECK_USER action...")
    await log_admin_action(
        admin_user_id="123456789",
        guild_id="987654321",
        action="RECHECK_USER",
        target_user_id="555666777",
        details={"rsi_handle": "TestUser", "status": "main"},
        status="success"
    )
    print("✅ RECHECK_USER logged\n")
    
    # Test 2: Log a bulk action
    print("Test 2: Logging BULK_RECHECK action...")
    await log_admin_action(
        admin_user_id="123456789",
        guild_id="987654321",
        action="BULK_RECHECK",
        details={"user_count": 25, "rejected": 5},
        status="success"
    )
    print("✅ BULK_RECHECK logged\n")
    
    # Test 3: Log a voice reset action
    print("Test 3: Logging RESET_VOICE_ALL action...")
    await log_admin_action(
        admin_user_id="123456789",
        guild_id="987654321",
        action="RESET_VOICE_ALL",
        details={"confirmed": True, "channels_deleted": 10},
        status="success"
    )
    print("✅ RESET_VOICE_ALL logged\n")
    
    # Test 4: Log an error status
    print("Test 4: Logging failed action...")
    await log_admin_action(
        admin_user_id="123456789",
        guild_id="987654321",
        action="RECHECK_USER",
        target_user_id="111222333",
        details={"error": "Rate limited"},
        status="rate_limited",
    )
    print("✅ Error action logged\n")

    # Query and display recent logs
    print("📋 Recent Audit Logs:")
    print("-" * 80)
    async with Database.get_connection() as db:
        cursor = await db.execute(
            """SELECT timestamp, admin_user_id, action,
                      target_user_id, status, details
               FROM admin_action_log
               ORDER BY timestamp DESC
               LIMIT 10"""
        )
        rows = await cursor.fetchall()

        if rows:
            for row in rows:
                timestamp, admin_id, action, target_id, status, details = row

                dt = datetime.fromtimestamp(timestamp, tz=UTC).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                print(f"[{dt}] {action}")
                print(f"  Admin: {admin_id} | Target: {target_id or 'N/A'}")
                print(f"  Status: {status}")
                if details:
                    print(f"  Details: {details}")
                print()
        else:
            print("No audit logs found.")

    print("-" * 80)
    print("\n✅ All audit logging tests completed successfully!")
    print("\n💡 To view logs in sqlite3:")
    print('   sqlite3 TESTDatabase.db "SELECT * FROM admin_action_log"')


if __name__ == "__main__":
    asyncio.run(test_audit_logging())

