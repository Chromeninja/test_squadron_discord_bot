# Bot/app/repositories/verification_repo.py

from typing import Optional
from helpers.database import Database
from helpers.logger import get_logger

logger = get_logger(__name__)


class VerificationRepository:
    """
    Repository for managing verification message IDs in the database.
    
    This repository handles the persistence of verification message IDs
    that were previously stored in JSON files.
    """

    @staticmethod
    async def get_verification_message_id(guild_id: int) -> Optional[int]:
        """
        Get the verification message ID for a guild.
        
        Args:
            guild_id: The Discord guild ID
            
        Returns:
            The message ID if found, None otherwise
        """
        try:
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    "SELECT message_id FROM verification_message WHERE guild_id = ?",
                    (guild_id,)
                )
                row = await cursor.fetchone()
                if row:
                    logger.debug(f"Retrieved verification message ID {row[0]} for guild {guild_id}")
                    return row[0]
                logger.debug(f"No verification message ID found for guild {guild_id}")
                return None
        except Exception as e:
            logger.error(f"Failed to get verification message ID for guild {guild_id}: {e}")
            return None

    @staticmethod
    async def set_verification_message_id(guild_id: int, message_id: int) -> None:
        """
        Set the verification message ID for a guild.
        
        Args:
            guild_id: The Discord guild ID
            message_id: The Discord message ID to store
        """
        try:
            async with Database.get_connection() as db:
                await db.execute(
                    """
                    INSERT OR REPLACE INTO verification_message (guild_id, message_id)
                    VALUES (?, ?)
                    """,
                    (guild_id, message_id)
                )
                await db.commit()
                logger.info(f"Set verification message ID {message_id} for guild {guild_id}")
        except Exception as e:
            logger.error(f"Failed to set verification message ID for guild {guild_id}: {e}")
            raise

    @staticmethod
    async def delete_verification_message_id(guild_id: int) -> None:
        """
        Delete the verification message ID for a guild.
        
        Args:
            guild_id: The Discord guild ID
        """
        try:
            async with Database.get_connection() as db:
                await db.execute(
                    "DELETE FROM verification_message WHERE guild_id = ?",
                    (guild_id,)
                )
                await db.commit()
                logger.info(f"Deleted verification message ID for guild {guild_id}")
        except Exception as e:
            logger.error(f"Failed to delete verification message ID for guild {guild_id}: {e}")
            raise
