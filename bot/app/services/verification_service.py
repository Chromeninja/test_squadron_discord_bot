# Bot/app/services/verification_service.py

from dataclasses import dataclass
from typing import Optional, Tuple, Any, Dict
import discord

from helpers.logger import get_logger
from helpers.http_helper import NotFoundError
from helpers.snapshots import snapshot_member_state, diff_snapshots
from helpers.leadership_log import ChangeSet, EventType
from helpers.task_queue import flush_tasks

logger = get_logger(__name__)


@dataclass
class VerificationResult:
    """Result of a verification operation."""
    success: bool
    status_info: Optional[str] = None  # New membership status or tuple of (old, new)
    message: Optional[str] = None  # Error message if not successful
    changes: Optional[Dict[str, Any]] = None  # Snapshot diff for logging
    handle_404: bool = False  # True if RSI handle was not found


class VerificationService:
    """
    Service class that encapsulates the verification workflow.
    
    This service orchestrates the complete verification process including:
    - RSI handle validation
    - Database updates
    - Role assignment
    - Snapshot tracking
    - Leadership logging
    - Announcement events
    """

    def __init__(self, http_client=None, leadership_log_service=None, announcement_service=None):
        """
        Initialize the verification service.
        
        Args:
            http_client: HTTP client for RSI API calls (injectable for testing)
            leadership_log_service: Service for leadership logging
            announcement_service: Service for announcement events
        """
        self.http_client = http_client
        self.leadership_log_service = leadership_log_service
        self.announcement_service = announcement_service
        
    async def verify_user(
        self, 
        guild: discord.Guild, 
        member: discord.Member, 
        rsi_handle: str,
        bot=None,
        event_type: EventType = EventType.VERIFICATION,
        initiator_kind: str = 'User',
        initiator_name: Optional[str] = None,
        notes: Optional[str] = None
    ) -> VerificationResult:
        """
        Verify a user's RSI handle and update their roles/status.
        
        Args:
            guild: Discord guild
            member: Discord member to verify
            rsi_handle: RSI handle to verify
            bot: Bot instance (for accessing config and role cache)
            event_type: Type of verification event (VERIFY, RECHECK, etc.)
            initiator_kind: Who initiated the verification ('User', 'Admin', etc.)
            initiator_name: Name of the initiator (if applicable)
            notes: Additional notes for logging
            
        Returns:
            VerificationResult with success status and details
        """
        if not bot:
            return VerificationResult(
                success=False,
                message="Bot instance is required for verification"
            )

        # Take snapshot before verification
        before_snap = await snapshot_member_state(bot, member)
        
        try:
            # Attempt verification through existing role_helper
            success, status_info, error_message = await self._reverify_member_internal(
                member, rsi_handle, bot
            )
            
            if not success:
                return VerificationResult(
                    success=False,
                    message=error_message or "Verification failed"
                )
            
            # Wait for queued tasks to complete before taking after snapshot
            try:
                await flush_tasks()
            except Exception:
                pass
                
            # Refresh member to get latest state after role changes
            try:
                refreshed = await member.guild.fetch_member(member.id)
                if refreshed:
                    member = refreshed
            except Exception:
                pass
                
            # Take snapshot after verification
            after_snap = await snapshot_member_state(bot, member)
            diff = diff_snapshots(before_snap, after_snap)
            
            # Handle nickname changes if flagged
            try:
                if (diff.get('username_before') == diff.get('username_after') and 
                    getattr(member, '_nickname_changed_flag', False)):
                    pref = getattr(member, '_preferred_verification_nick', None)
                    if pref and pref != diff.get('username_before'):
                        diff['username_after'] = pref
            except Exception:
                pass
            
            # Create and post leadership log changeset
            cs = ChangeSet(
                user_id=member.id,
                event=event_type,
                initiator_kind=initiator_kind,
                initiator_name=initiator_name,
                notes=notes,
            )
            for k, v in diff.items():
                setattr(cs, k, v)
                
            try:
                if self.leadership_log_service:
                    await self.leadership_log_service.post_if_changed(cs)
                else:
                    # Fallback to direct helper call for backward compatibility
                    from helpers.leadership_log import post_if_changed
                    await post_if_changed(bot, cs)
            except Exception as e:
                logger.debug(f"Leadership log post failed: {e}")
            
            # Enqueue verification event for announcements if this was a new verification
            if event_type == EventType.VERIFICATION:
                try:
                    new_status = status_info[1] if isinstance(status_info, tuple) else status_info
                    old_status = status_info[0] if isinstance(status_info, tuple) else diff.get('status_before', 'non_member')
                    if self.announcement_service:
                        await self.announcement_service.enqueue_verification_event(
                            member.id, old_status or "non_member", new_status
                        )
                    else:
                        # Fallback to direct helper call for backward compatibility
                        from helpers.announcement import enqueue_verification_event
                        await enqueue_verification_event(member, old_status or "non_member", new_status)
                except Exception as e:
                    logger.debug(f"Failed to enqueue verification event: {e}")
            
            return VerificationResult(
                success=True,
                status_info=status_info,
                changes=diff
            )
            
        except NotFoundError:
            # RSI handle not found - caller should handle 404 remediation
            return VerificationResult(
                success=False,
                handle_404=True,
                message="RSI handle not found"
            )
        except Exception as e:
            logger.error(f"Verification service error: {e}")
            return VerificationResult(
                success=False,
                message=f"Verification failed: {str(e)}"
            )

    async def _reverify_member_internal(
        self, 
        member: discord.Member, 
        rsi_handle: str, 
        bot
    ) -> Tuple[bool, Any, Optional[str]]:
        """
        Internal method that handles the core RSI verification logic.
        This mirrors the existing reverify_member function.
        """
        from verification.rsi_verification import is_valid_rsi_handle
        from helpers.role_helper import assign_roles

        # Use injected http_client if available, otherwise use bot's
        http_client = self.http_client or bot.http_client
        
        verify_value, cased_handle, community_moniker = await is_valid_rsi_handle(
            rsi_handle, http_client
        )  # May raise NotFoundError

        if verify_value is None or cased_handle is None:
            return False, "unknown", "Failed to verify RSI handle."

        role_type = await assign_roles(
            member, verify_value, cased_handle, bot, community_moniker=community_moniker
        )
        return True, role_type, None
