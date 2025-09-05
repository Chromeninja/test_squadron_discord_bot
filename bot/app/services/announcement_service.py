# bot/app/services/announcement_service.py
"""
Announcement Service

Provides a clean API for announcement functionality while encapsulating
the existing helper implementation details.
"""

import time
from typing import Optional
from datetime import datetime, timezone

from helpers.logger import get_logger
from helpers.announcement import enqueue_verification_event as helper_enqueue_verification_event

logger = get_logger(__name__)


class AnnouncementService:
    """
    Service façade for announcement functionality.
    
    Encapsulates bulk announcement queue operations and provides
    a clean interface for app-level code.
    """

    def __init__(self, bot):
        """Initialize the announcement service with bot reference."""
        self.bot = bot
        # Get BulkAnnouncer cog for flush operations
        self._bulk_announcer = None
        logger.debug("AnnouncementService initialized")

    def _get_bulk_announcer(self):
        """Get the BulkAnnouncer cog instance."""
        if self._bulk_announcer is None:
            self._bulk_announcer = self.bot.get_cog("BulkAnnouncer")
        return self._bulk_announcer

    async def enqueue_verification_event(self, member_id: int, old_status: str, new_status: str) -> bool:
        """
        Enqueue a verification status change event for bulk announcement.
        
        Args:
            member_id: Discord member ID
            old_status: Previous membership status
            new_status: New membership status
            
        Returns:
            True if successfully enqueued, False otherwise
        """
        try:
            # Get member object for the helper function
            member = None
            for guild in self.bot.guilds:
                member = guild.get_member(member_id)
                if member:
                    break
                    
            if not member:
                logger.warning(f"Could not find member {member_id} for announcement event")
                return False
                
            # Use existing helper implementation
            await helper_enqueue_verification_event(member, old_status, new_status)
            logger.debug(f"Enqueued verification event for member {member_id}: {old_status} -> {new_status}")
            return True
            
        except Exception as e:
            logger.exception(f"Error enqueuing verification event for member {member_id}: {e}")
            return False

    async def flush_daily(self, now_utc: Optional[datetime] = None) -> bool:
        """
        Perform daily flush of pending announcements.
        
        Args:
            now_utc: Optional current UTC time (for testing)
            
        Returns:
            True if announcements were sent, False otherwise
        """
        try:
            bulk_announcer = self._get_bulk_announcer()
            if not bulk_announcer:
                logger.warning("BulkAnnouncer cog not found for daily flush")
                return False
                
            result = await bulk_announcer.flush_pending()
            if result:
                logger.info("Daily announcement flush completed successfully")
            else:
                logger.debug("Daily announcement flush: no pending announcements")
            return result
            
        except Exception as e:
            logger.exception(f"Error during daily announcement flush: {e}")
            return False

    async def flush_if_threshold(self, now_utc: Optional[datetime] = None) -> bool:
        """
        Check threshold and flush if needed.
        
        Args:
            now_utc: Optional current UTC time (for testing)
            
        Returns:
            True if announcements were sent, False otherwise
        """
        try:
            bulk_announcer = self._get_bulk_announcer()
            if not bulk_announcer:
                logger.debug("BulkAnnouncer cog not found for threshold check")
                return False
                
            # Check current pending count against threshold
            pending = await bulk_announcer._count_pending()
            if pending >= bulk_announcer.threshold:
                logger.info(f"Threshold reached ({pending} >= {bulk_announcer.threshold}), flushing announcements")
                result = await bulk_announcer.flush_pending()
                return result
            else:
                logger.debug(f"Threshold not reached ({pending} < {bulk_announcer.threshold})")
                return False
                
        except Exception as e:
            logger.exception(f"Error during threshold announcement flush: {e}")
            return False

    async def get_pending_count(self) -> int:
        """
        Get the number of pending announcement events.
        
        Returns:
            Number of pending events, or 0 if error
        """
        try:
            bulk_announcer = self._get_bulk_announcer()
            if not bulk_announcer:
                return 0
                
            return await bulk_announcer._count_pending()
            
        except Exception as e:
            logger.exception(f"Error getting pending announcement count: {e}")
            return 0

    async def flush_pending(self) -> bool:
        """
        Manually flush all pending announcements.
        
        Returns:
            True if announcements were sent, False otherwise
        """
        try:
            bulk_announcer = self._get_bulk_announcer()
            if not bulk_announcer:
                logger.warning("BulkAnnouncer cog not found for manual flush")
                return False
                
            result = await bulk_announcer.flush_pending()
            if result:
                logger.info("Manual announcement flush completed successfully")
            return result
            
        except Exception as e:
            logger.exception(f"Error during manual announcement flush: {e}")
            return False
