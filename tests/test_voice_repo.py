"""
Tests for the voice repository functions.

This file contains tests for the new voice repository functions,
focusing on scoped deletion and proper guild/JTC channel handling.
"""

import asyncio
import os
import pytest
import time
from unittest.mock import patch, MagicMock

from helpers.database import Database
from helpers.voice_repo import (
    get_stale_voice_entries,
    cleanup_user_voice_data,
    get_user_channel_id,
    upsert_channel_settings,
    list_permissions,
    set_feature_row,
    transfer_channel_owner
)
import pytest_asyncio


@pytest_asyncio.fixture
async def test_db():
    """Set up a test database."""
    test_db_path = "test_voice_repo.db"
    # Remove the test database if it exists
    if os.path.exists(test_db_path):
        os.unlink(test_db_path)
    
    # Initialize the database with the test path
    await Database.initialize(test_db_path)
    
    # Make sure the schema is properly initialized 
    # by executing required SQL to create tables for testing
    async with Database.get_connection() as db:
        # User voice channels table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS user_voice_channels (
                guild_id INTEGER NOT NULL,
                jtc_channel_id INTEGER NOT NULL,
                owner_id INTEGER NOT NULL,
                voice_channel_id INTEGER NOT NULL,
                created_at INTEGER DEFAULT (strftime('%s','now')),
                PRIMARY KEY (guild_id, jtc_channel_id, owner_id)
            )
            """
        )
        
        # Voice cooldowns table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS voice_cooldowns (
                guild_id INTEGER NOT NULL,
                jtc_channel_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                timestamp INTEGER NOT NULL,
                PRIMARY KEY (guild_id, jtc_channel_id, user_id)
            )
            """
        )
        
        # Channel settings table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS channel_settings (
                guild_id INTEGER NOT NULL,
                jtc_channel_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                channel_name TEXT,
                user_limit INTEGER,
                lock INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, jtc_channel_id, user_id)
            )
            """
        )
        
        # Channel permissions table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS channel_permissions (
                guild_id INTEGER NOT NULL,
                jtc_channel_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                target_type TEXT NOT NULL,
                permission TEXT NOT NULL,
                PRIMARY KEY (guild_id, jtc_channel_id, user_id, target_id, target_type)
            )
            """
        )
        
        # Channel PTT settings table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS channel_ptt_settings (
                guild_id INTEGER NOT NULL,
                jtc_channel_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                target_type TEXT NOT NULL,
                ptt_enabled BOOLEAN NOT NULL,
                PRIMARY KEY (guild_id, jtc_channel_id, user_id, target_id, target_type)
            )
            """
        )
        
        # Channel priority speaker settings table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS channel_priority_speaker_settings (
                guild_id INTEGER NOT NULL,
                jtc_channel_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                target_type TEXT NOT NULL,
                priority_enabled BOOLEAN NOT NULL,
                PRIMARY KEY (guild_id, jtc_channel_id, user_id, target_id, target_type)
            )
            """
        )
        
        # Channel soundboard settings table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS channel_soundboard_settings (
                guild_id INTEGER NOT NULL,
                jtc_channel_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                target_type TEXT NOT NULL,
                soundboard_enabled BOOLEAN NOT NULL,
                PRIMARY KEY (guild_id, jtc_channel_id, user_id, target_id, target_type)
            )
            """
        )
        
        await db.commit()
    
    yield test_db_path
    
    # Clean up
    if os.path.exists(test_db_path):
        os.unlink(test_db_path)


async def setup_test_data(db):
    """Set up test data for the voice repository tests."""
    # Clear any existing data
    tables = [
        "user_voice_channels", 
        "voice_cooldowns", 
        "channel_settings", 
        "channel_permissions",
        "channel_ptt_settings",
        "channel_priority_speaker_settings",
        "channel_soundboard_settings"
    ]
    
    for table in tables:
        await db.execute(f"DELETE FROM {table}")
    
    # Guild 1, JTC 1
    await db.execute(
        """
        INSERT INTO user_voice_channels 
        (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (1, 101, 1001, 5001, int(time.time()))
    )
    
    # Guild 1, JTC 2
    await db.execute(
        """
        INSERT INTO user_voice_channels 
        (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (1, 102, 1001, 5002, int(time.time()))
    )
    
    # Guild 2, JTC 1
    await db.execute(
        """
        INSERT INTO user_voice_channels 
        (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (2, 101, 1001, 5003, int(time.time()))
    )
    
    # Set up cooldowns
    await db.execute(
        """
        INSERT INTO voice_cooldowns 
        (guild_id, jtc_channel_id, user_id, timestamp)
        VALUES (?, ?, ?, ?)
        """,
        (1, 101, 1001, int(time.time()) - 3600)  # 1 hour ago
    )
    
    await db.execute(
        """
        INSERT INTO voice_cooldowns 
        (guild_id, jtc_channel_id, user_id, timestamp)
        VALUES (?, ?, ?, ?)
        """,
        (1, 102, 1001, int(time.time()))  # Current time
    )
    
    await db.execute(
        """
        INSERT INTO voice_cooldowns 
        (guild_id, jtc_channel_id, user_id, timestamp)
        VALUES (?, ?, ?, ?)
        """,
        (2, 101, 1001, int(time.time()) - 7200)  # 2 hours ago
    )
    
    # Add channel settings
    await db.execute(
        """
        INSERT INTO channel_settings 
        (guild_id, jtc_channel_id, user_id, channel_name, user_limit, lock)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (1, 101, 1001, 'Test Channel 1', 5, 0)
    )
    
    await db.execute(
        """
        INSERT INTO channel_settings 
        (guild_id, jtc_channel_id, user_id, channel_name, user_limit, lock)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (1, 102, 1001, 'Test Channel 2', 10, 1)
    )
    
    # Add permissions
    await db.execute(
        """
        INSERT INTO channel_permissions 
        (guild_id, jtc_channel_id, user_id, target_id, target_type, permission)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (1, 101, 1001, 2001, 'user', 'permit')
    )
    
    await db.execute(
        """
        INSERT INTO channel_permissions 
        (guild_id, jtc_channel_id, user_id, target_id, target_type, permission)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (1, 101, 1001, 3001, 'role', 'reject')
    )
    
    await db.commit()


@pytest.mark.asyncio
async def test_get_stale_voice_entries(test_db):
    """Test getting stale voice entries."""
    async with Database.get_connection() as db:
        await setup_test_data(db)
        
        # Set one entry to be older than cutoff
        old_timestamp = int(time.time()) - 86400  # 1 day ago
        await db.execute(
            """
            UPDATE voice_cooldowns 
            SET timestamp = ? 
            WHERE guild_id = 1 AND jtc_channel_id = 101 AND user_id = 1001
            """,
            (old_timestamp,)
        )
        await db.commit()
        
        # Get stale entries with a cutoff of 12 hours
        cutoff = int(time.time()) - 43200  # 12 hours ago
        stale_entries = await get_stale_voice_entries(cutoff)
        
        # Should only get the one we set to be old
        assert len(stale_entries) == 1
        assert stale_entries[0] == (1, 101, 1001)


@pytest.mark.asyncio
async def test_cleanup_user_voice_data(test_db):
    """Test cleaning up user voice data for a specific guild and JTC."""
    async with Database.get_connection() as db:
        await setup_test_data(db)
        
        # Clean up guild 1, JTC 101 for user 1001
        await cleanup_user_voice_data(1, 101, 1001)
        
        # Check that data for guild 1, JTC 101 was deleted
        cursor = await db.execute(
            """
            SELECT 1 FROM user_voice_channels 
            WHERE guild_id = 1 AND jtc_channel_id = 101 AND owner_id = 1001
            """
        )
        assert await cursor.fetchone() is None
        
        cursor = await db.execute(
            """
            SELECT 1 FROM channel_settings 
            WHERE guild_id = 1 AND jtc_channel_id = 101 AND user_id = 1001
            """
        )
        assert await cursor.fetchone() is None
        
        cursor = await db.execute(
            """
            SELECT 1 FROM channel_permissions 
            WHERE guild_id = 1 AND jtc_channel_id = 101 AND user_id = 1001
            """
        )
        assert await cursor.fetchone() is None
        
        # Check that data for guild 1, JTC 102 was NOT deleted
        cursor = await db.execute(
            """
            SELECT 1 FROM user_voice_channels 
            WHERE guild_id = 1 AND jtc_channel_id = 102 AND owner_id = 1001
            """
        )
        assert await cursor.fetchone() is not None
        
        # Check that data for guild 2, JTC 101 was NOT deleted
        cursor = await db.execute(
            """
            SELECT 1 FROM user_voice_channels 
            WHERE guild_id = 2 AND jtc_channel_id = 101 AND owner_id = 1001
            """
        )
        assert await cursor.fetchone() is not None


@pytest.mark.asyncio
async def test_get_user_channel_id(test_db):
    """Test getting a user's channel ID."""
    async with Database.get_connection() as db:
        await setup_test_data(db)
        
        # Get channel for guild 1, JTC 101
        channel_id = await get_user_channel_id(1001, 1, 101)
        assert channel_id == 5001
        
        # Get channel for guild 1, JTC 102
        channel_id = await get_user_channel_id(1001, 1, 102)
        assert channel_id == 5002
        
        # Get channel for non-existent guild/JTC
        channel_id = await get_user_channel_id(1001, 3, 101)
        assert channel_id is None


@pytest.mark.asyncio
async def test_upsert_channel_settings(test_db):
    """Test upserting channel settings."""
    async with Database.get_connection() as db:
        await setup_test_data(db)
        
        # Update existing settings
        await upsert_channel_settings(1001, 1, 101, channel_name="Updated Channel", user_limit=15)
        
        cursor = await db.execute(
            """
            SELECT channel_name, user_limit FROM channel_settings 
            WHERE guild_id = 1 AND jtc_channel_id = 101 AND user_id = 1001
            """
        )
        row = await cursor.fetchone()
        assert row["channel_name"] == "Updated Channel"
        assert row["user_limit"] == 15
        
        # Insert new settings
        await upsert_channel_settings(2001, 1, 101, channel_name="New Channel", user_limit=20, lock=1)
        
        cursor = await db.execute(
            """
            SELECT channel_name, user_limit, lock FROM channel_settings 
            WHERE guild_id = 1 AND jtc_channel_id = 101 AND user_id = 2001
            """
        )
        row = await cursor.fetchone()
        assert row["channel_name"] == "New Channel"
        assert row["user_limit"] == 20
        assert row["lock"] == 1


@pytest.mark.asyncio
async def test_list_permissions(test_db):
    """Test listing permissions."""
    async with Database.get_connection() as db:
        await setup_test_data(db)
        
        # List permissions
        permissions = await list_permissions(1001, 1, 101, "channel_permissions")
        assert len(permissions) == 2
        
        # Check specific permission entry
        user_permit = next(p for p in permissions if p["target_id"] == 2001)
        assert user_permit["target_type"] == "user"
        assert user_permit["permission"] == "permit"
        
        role_reject = next(p for p in permissions if p["target_id"] == 3001)
        assert role_reject["target_type"] == "role"
        assert role_reject["permission"] == "reject"


@pytest.mark.asyncio
async def test_set_feature_row(test_db):
    """Test setting a feature row."""
    async with Database.get_connection() as db:
        await setup_test_data(db)
        
        # Set a new PTT setting
        await set_feature_row(
            "channel_ptt_settings", 1001, 1, 101, 2001, "user", True
        )
        
        cursor = await db.execute(
            """
            SELECT ptt_enabled FROM channel_ptt_settings 
            WHERE guild_id = 1 AND jtc_channel_id = 101 AND user_id = 1001 AND target_id = 2001
            """
        )
        row = await cursor.fetchone()
        assert row["ptt_enabled"] == 1  # SQLite stores booleans as 0/1
        
        # Update the PTT setting
        await set_feature_row(
            "channel_ptt_settings", 1001, 1, 101, 2001, "user", False
        )
        
        cursor = await db.execute(
            """
            SELECT ptt_enabled FROM channel_ptt_settings 
            WHERE guild_id = 1 AND jtc_channel_id = 101 AND user_id = 1001 AND target_id = 2001
            """
        )
        row = await cursor.fetchone()
        assert row["ptt_enabled"] == 0  # SQLite stores booleans as 0/1


@pytest.mark.asyncio
async def test_transfer_channel_owner(test_db):
    """Test transferring channel ownership."""
    async with Database.get_connection() as db:
        await setup_test_data(db)
        
        # Add a permission for the new owner to verify it doesn't get duplicated
        await db.execute(
            """
            INSERT INTO channel_permissions 
            (guild_id, jtc_channel_id, user_id, target_id, target_type, permission)
            VALUES (1, 101, 2001, 3002, 'role', 'permit')
            """
        )
        await db.commit()
        
        # Transfer ownership
        success = await transfer_channel_owner(5001, 2001, 1, 101)
        assert success is True
        
        # Check that ownership was transferred
        cursor = await db.execute(
            """
            SELECT owner_id FROM user_voice_channels 
            WHERE voice_channel_id = 5001
            """
        )
        row = await cursor.fetchone()
        assert row["owner_id"] == 2001
        
        # Check that settings were transferred
        cursor = await db.execute(
            """
            SELECT channel_name, user_limit FROM channel_settings 
            WHERE guild_id = 1 AND jtc_channel_id = 101 AND user_id = 2001
            """
        )
        row = await cursor.fetchone()
        assert row["channel_name"] == "Test Channel 1"
        assert row["user_limit"] == 5
        
        # Check that permissions were transferred
        cursor = await db.execute(
            """
            SELECT COUNT(*) as count FROM channel_permissions 
            WHERE guild_id = 1 AND jtc_channel_id = 101 AND user_id = 2001
            """
        )
        row = await cursor.fetchone()
        assert row["count"] == 2  # Original permissions were transferred
        
        # Check for cooldown entry
        cursor = await db.execute(
            """
            SELECT 1 FROM voice_cooldowns 
            WHERE guild_id = 1 AND jtc_channel_id = 101 AND user_id = 2001
            """
        )
        assert await cursor.fetchone() is not None
