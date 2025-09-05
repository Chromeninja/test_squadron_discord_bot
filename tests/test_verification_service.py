"""Tests for the VerificationService."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from bot.app.services.verification_service import VerificationService, VerificationResult
from helpers.leadership_log import EventType
from helpers.http_helper import NotFoundError


@pytest.fixture
def mock_guild():
    """Create a mock Discord guild."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = 12345
    return guild


@pytest.fixture
def mock_member():
    """Create a mock Discord member."""
    member = MagicMock(spec=discord.Member)
    member.id = 67890
    member.guild = MagicMock()
    member.guild.fetch_member = AsyncMock(return_value=member)
    return member


@pytest.fixture
def mock_bot():
    """Create a mock bot instance."""
    bot = MagicMock()
    bot.http_client = MagicMock()
    return bot


@pytest.fixture
def verification_service():
    """Create a VerificationService instance."""
    return VerificationService()


@pytest.mark.asyncio
async def test_verify_user_success(verification_service, mock_guild, mock_member, mock_bot):
    """Test successful user verification."""
    with patch('bot.app.services.verification_service.snapshot_member_state') as mock_snapshot, \
         patch('bot.app.services.verification_service.flush_tasks') as mock_flush, \
         patch('bot.app.services.verification_service.diff_snapshots') as mock_diff, \
         patch('helpers.leadership_log.post_if_changed') as mock_post, \
         patch('helpers.announcement.enqueue_verification_event') as mock_enqueue, \
         patch.object(verification_service, '_reverify_member_internal') as mock_reverify:
        
        # Setup mocks
        mock_snapshot.return_value = {'username_before': 'oldname'}
        mock_diff.return_value = {'username_before': 'oldname', 'username_after': 'newname'}
        mock_reverify.return_value = (True, 'member', None)
        
        result = await verification_service.verify_user(
            guild=mock_guild,
            member=mock_member,
            rsi_handle='testhandle',
            bot=mock_bot,
            event_type=EventType.VERIFICATION
        )
        
        assert result.success is True
        assert result.status_info == 'member'
        assert result.changes is not None
        assert result.handle_404 is False
        
        # Verify that key functions were called
        mock_reverify.assert_called_once_with(mock_member, 'testhandle', mock_bot)
        mock_post.assert_called_once()
        mock_enqueue.assert_called_once()


@pytest.mark.asyncio
async def test_verify_user_handle_404(verification_service, mock_guild, mock_member, mock_bot):
    """Test verification with RSI handle not found."""
    with patch.object(verification_service, '_reverify_member_internal') as mock_reverify:
        mock_reverify.side_effect = NotFoundError("Handle not found")
        
        result = await verification_service.verify_user(
            guild=mock_guild,
            member=mock_member,
            rsi_handle='nonexistenthandle',
            bot=mock_bot
        )
        
        assert result.success is False
        assert result.handle_404 is True
        assert result.message == "RSI handle not found"


@pytest.mark.asyncio
async def test_verify_user_failure(verification_service, mock_guild, mock_member, mock_bot):
    """Test verification failure."""
    with patch.object(verification_service, '_reverify_member_internal') as mock_reverify:
        mock_reverify.return_value = (False, None, "Verification failed")
        
        result = await verification_service.verify_user(
            guild=mock_guild,
            member=mock_member,
            rsi_handle='testhandle',
            bot=mock_bot
        )
        
        assert result.success is False
        assert result.handle_404 is False
        assert result.message == "Verification failed"


@pytest.mark.asyncio
async def test_verify_user_no_bot():
    """Test verification without bot instance."""
    service = VerificationService()
    
    result = await service.verify_user(
        guild=MagicMock(),
        member=MagicMock(),
        rsi_handle='testhandle',
        bot=None
    )
    
    assert result.success is False
    assert "Bot instance is required" in result.message


@pytest.mark.asyncio
async def test_reverify_member_internal(verification_service, mock_member, mock_bot):
    """Test the internal reverify member method."""
    with patch('verification.rsi_verification.is_valid_rsi_handle') as mock_valid, \
         patch('helpers.role_helper.assign_roles') as mock_assign:
        
        mock_valid.return_value = (True, 'TestHandle', 'TestOrg')
        mock_assign.return_value = 'member'
        
        success, status_info, error = await verification_service._reverify_member_internal(
            mock_member, 'testhandle', mock_bot
        )
        
        assert success is True
        assert status_info == 'member'
        assert error is None
        
        mock_valid.assert_called_once_with('testhandle', mock_bot.http_client)
        mock_assign.assert_called_once_with(
            mock_member, True, 'TestHandle', mock_bot, community_moniker='TestOrg'
        )


def test_verification_result_dataclass():
    """Test VerificationResult dataclass."""
    result = VerificationResult(success=True, status_info='member')
    
    assert result.success is True
    assert result.status_info == 'member'
    assert result.message is None
    assert result.changes is None
    assert result.handle_404 is False
