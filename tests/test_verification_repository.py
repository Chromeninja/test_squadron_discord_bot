import pytest
import os
import importlib.util



@pytest.mark.asyncio
async def test_verification_repository_basic_operations(temp_db):
    """Test basic CRUD operations for VerificationRepository."""
    # Import the repository
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo_path = os.path.join(current_dir, "bot", "app", "repositories", "verification_repo.py")
    spec = importlib.util.spec_from_file_location("verification_repo", repo_path)
    verification_repo_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verification_repo_module)
    VerificationRepository = verification_repo_module.VerificationRepository

    test_guild_id = 123456789
    test_message_id = 987654321

    # Test get non-existent
    result = await VerificationRepository.get_verification_message_id(test_guild_id)
    assert result is None

    # Test set
    await VerificationRepository.set_verification_message_id(test_guild_id, test_message_id)

    # Test get existing
    result = await VerificationRepository.get_verification_message_id(test_guild_id)
    assert result == test_message_id

    # Test update (insert or replace)
    new_message_id = 111222333
    await VerificationRepository.set_verification_message_id(test_guild_id, new_message_id)
    result = await VerificationRepository.get_verification_message_id(test_guild_id)
    assert result == new_message_id

    # Test delete
    await VerificationRepository.delete_verification_message_id(test_guild_id)
    result = await VerificationRepository.get_verification_message_id(test_guild_id)
    assert result is None


@pytest.mark.asyncio
async def test_verification_repository_multiple_guilds(temp_db):
    """Test that the repository correctly handles multiple guilds."""
    # Import the repository
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo_path = os.path.join(current_dir, "bot", "app", "repositories", "verification_repo.py")
    spec = importlib.util.spec_from_file_location("verification_repo", repo_path)
    verification_repo_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verification_repo_module)
    VerificationRepository = verification_repo_module.VerificationRepository

    guild1_id = 111111111
    guild2_id = 222222222
    message1_id = 333333333
    message2_id = 444444444

    # Set different message IDs for different guilds
    await VerificationRepository.set_verification_message_id(guild1_id, message1_id)
    await VerificationRepository.set_verification_message_id(guild2_id, message2_id)

    # Verify they're stored correctly and don't interfere
    result1 = await VerificationRepository.get_verification_message_id(guild1_id)
    result2 = await VerificationRepository.get_verification_message_id(guild2_id)

    assert result1 == message1_id
    assert result2 == message2_id

    # Delete one and verify the other remains
    await VerificationRepository.delete_verification_message_id(guild1_id)
    
    result1_after_delete = await VerificationRepository.get_verification_message_id(guild1_id)
    result2_after_delete = await VerificationRepository.get_verification_message_id(guild2_id)

    assert result1_after_delete is None
    assert result2_after_delete == message2_id
