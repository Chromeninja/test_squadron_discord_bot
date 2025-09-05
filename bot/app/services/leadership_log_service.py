# bot/app/services/leadership_log_service.py
"""
Leadership Log Service

Provides a clean API for leadership logging functionality while encapsulating
the existing helper implementation details.
"""

from typing import Union, Optional
from helpers.logger import get_logger
from helpers.leadership_log import ChangeSet, EventType, post_if_changed as helper_post_if_changed

logger = get_logger(__name__)


class LeadershipLogService:
    """
    Service façade for leadership logging functionality.
    
    Encapsulates leadership log posting and deduplication logic while
    providing a clean interface for app-level code.
    """

    def __init__(self, bot):
        """Initialize the leadership log service with bot reference."""
        self.bot = bot
        logger.debug("LeadershipLogService initialized")

    async def post_if_changed(self, diff_or_changeset: Union[dict, ChangeSet]) -> bool:
        """
        Post a leadership log entry if there are material changes.
        
        Args:
            diff_or_changeset: Either a legacy diff dict or a ChangeSet object
            
        Returns:
            True if a log entry was posted, False otherwise
        """
        try:
            # Normalize input to ChangeSet
            if isinstance(diff_or_changeset, ChangeSet):
                changeset = diff_or_changeset
            else:
                # Convert legacy diff format to ChangeSet
                changeset = self._normalize_diff_to_changeset(diff_or_changeset)
                
            if not changeset:
                logger.debug("Could not normalize diff to ChangeSet, skipping leadership log")
                return False
                
            # Use existing helper implementation with deduplication and suppression
            await helper_post_if_changed(self.bot, changeset)
            
            # The helper doesn't return a value, so we assume success if no exception
            logger.debug(f"Posted leadership log for user {changeset.user_id}")
            return True
            
        except Exception as e:
            logger.exception(f"Error posting leadership log: {e}")
            return False

    def _normalize_diff_to_changeset(self, diff: dict) -> Optional[ChangeSet]:
        """
        Convert a legacy diff dictionary to a ChangeSet object.
        
        Args:
            diff: Legacy diff dictionary
            
        Returns:
            ChangeSet object or None if conversion fails
        """
        try:
            # Extract required fields
            user_id = diff.get('user_id')
            if not user_id:
                logger.warning("Diff missing user_id, cannot create ChangeSet")
                return None
                
            # Determine event type from diff context
            event_type = EventType.VERIFICATION  # default
            if diff.get('is_recheck'):
                event_type = EventType.RECHECK
            elif diff.get('is_admin_check'):
                event_type = EventType.ADMIN_CHECK
            elif diff.get('is_auto_check'):
                event_type = EventType.AUTO_CHECK
                
            # Determine initiator
            initiator_kind = 'User'
            initiator_name = None
            if diff.get('by_admin'):
                initiator_kind = 'Admin'
                initiator_name = diff.get('by_admin')
            elif diff.get('is_auto_check'):
                initiator_kind = 'Auto'
                
            # Create ChangeSet
            changeset = ChangeSet(
                user_id=user_id,
                event=event_type,
                initiator_kind=initiator_kind,
                initiator_name=initiator_name,
                status_before=diff.get('status_before'),
                status_after=diff.get('status_after'),
                moniker_before=diff.get('moniker_before'),
                moniker_after=diff.get('moniker_after'),
                handle_before=diff.get('handle_before'),
                handle_after=diff.get('handle_after'),
                username_before=diff.get('username_before'),
                username_after=diff.get('username_after'),
                roles_added=diff.get('roles_added', []),
                roles_removed=diff.get('roles_removed', []),
                notes=diff.get('notes')
            )
            
            # Set duration if available
            if 'duration_ms' in diff:
                changeset.duration_ms = diff['duration_ms']
                
            return changeset
            
        except Exception as e:
            logger.exception(f"Error normalizing diff to ChangeSet: {e}")
            return None

    async def post_verification_log(self, user_id: int, old_status: str, new_status: str, 
                                   is_recheck: bool = False, by_admin: str = None,
                                   notes: str = None) -> bool:
        """
        Post a verification log entry.
        
        Args:
            user_id: Discord user ID
            old_status: Previous status
            new_status: New status
            is_recheck: Whether this is a recheck operation
            by_admin: Admin who initiated (if applicable)
            notes: Additional notes
            
        Returns:
            True if log entry was posted, False otherwise
        """
        try:
            event_type = EventType.RECHECK if is_recheck else EventType.VERIFICATION
            initiator_kind = 'Admin' if by_admin else 'User'
            
            changeset = ChangeSet(
                user_id=user_id,
                event=event_type,
                initiator_kind=initiator_kind,
                initiator_name=by_admin,
                status_before=old_status,
                status_after=new_status,
                notes=notes
            )
            
            return await self.post_if_changed(changeset)
            
        except Exception as e:
            logger.exception(f"Error posting verification log for user {user_id}: {e}")
            return False

    async def post_admin_check_log(self, user_id: int, admin_name: str,
                                  status_before: str = None, status_after: str = None,
                                  handle_before: str = None, handle_after: str = None,
                                  moniker_before: str = None, moniker_after: str = None,
                                  username_before: str = None, username_after: str = None,
                                  notes: str = None) -> bool:
        """
        Post an admin check log entry.
        
        Args:
            user_id: Discord user ID
            admin_name: Name of admin performing check
            status_before: Previous status
            status_after: New status
            handle_before: Previous handle
            handle_after: New handle
            moniker_before: Previous moniker
            moniker_after: New moniker
            username_before: Previous username
            username_after: New username
            notes: Additional notes
            
        Returns:
            True if log entry was posted, False otherwise
        """
        try:
            changeset = ChangeSet(
                user_id=user_id,
                event=EventType.ADMIN_CHECK,
                initiator_kind='Admin',
                initiator_name=admin_name,
                status_before=status_before,
                status_after=status_after,
                handle_before=handle_before,
                handle_after=handle_after,
                moniker_before=moniker_before,
                moniker_after=moniker_after,
                username_before=username_before,
                username_after=username_after,
                notes=notes
            )
            
            return await self.post_if_changed(changeset)
            
        except Exception as e:
            logger.exception(f"Error posting admin check log for user {user_id}: {e}")
            return False
