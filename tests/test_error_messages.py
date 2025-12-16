"""
Test user-facing error messages for voice commands.
"""

import pytest

from helpers.error_messages import format_user_error, format_user_success


class TestErrorMessages:
    """Test error message formatting."""

    def test_owner_present_message(self):
        """Test OWNER_PRESENT error message."""
        result = format_user_error("OWNER_PRESENT")
        assert "❌" in result
        assert "claim" in result.lower()
        assert "owner" in result.lower()
        assert "present" in result.lower()
        # Message should be concise
        assert len(result) < 200

    def test_not_in_voice_message(self):
        """Test NOT_IN_VOICE error message."""
        result = format_user_error("NOT_IN_VOICE")
        assert "❌" in result
        assert "voice" in result.lower()
        assert len(result) < 200

    def test_cooldown_message(self):
        """Test COOLDOWN error message with seconds."""
        result = format_user_error("COOLDOWN", seconds=5)
        assert "5s" in result or "5" in result
        assert "⚠️" in result or "❌" in result
        assert len(result) < 200

    def test_db_temp_error_message(self):
        """Test DB_TEMP_ERROR error message."""
        result = format_user_error("DB_TEMP_ERROR")
        assert "❌" in result
        assert (
            "database" in result.lower()
            or "temp" in result.lower()
            or "try again" in result.lower()
        )
        assert len(result) < 200

    def test_unknown_message(self):
        """Test UNKNOWN error message."""
        result = format_user_error("UNKNOWN")
        assert "❌" in result
        assert "wrong" in result.lower() or "error" in result.lower()
        assert len(result) < 200

    def test_unknown_error_code_fallback(self):
        """Test that unknown error codes fall back to UNKNOWN message."""
        result = format_user_error("INVALID_CODE_XYZ")
        assert "❌" in result
        assert "wrong" in result.lower() or "error" in result.lower()

    def test_missing_format_args_safety(self):
        """Test that missing format args don't crash."""
        # OWNER_PRESENT no longer requires args
        result = format_user_error("OWNER_PRESENT")
        assert "❌" in result
        assert "claim" in result.lower()

        # COOLDOWN still requires seconds but should handle missing gracefully
        result = format_user_error("COOLDOWN")
        assert "⚠️" in result or "❌" in result  # Should have an emoji
        # May have placeholder or original template

    @pytest.mark.parametrize(
        "code,kwargs",
        [
            ("OWNER_PRESENT", {"owner_display": "TestUser"}),
            ("NOT_IN_VOICE", {}),
            ("NOT_OWNER", {}),
            ("NOT_MANAGED", {}),
            ("COOLDOWN", {"seconds": 5}),
            ("DB_TEMP_ERROR", {}),
            ("PERMISSION", {}),
            ("UNKNOWN", {}),
            ("NO_CHANNEL", {}),
            ("NOT_IN_CHANNEL", {}),
            ("NO_JTC_CONFIGURED", {}),
            ("JTC_NOT_FOUND", {}),
            ("CREATION_FAILED", {}),
        ],
    )
    def test_all_messages_have_emoji(self, code, kwargs):
        """Test that all error messages start with an emoji."""
        result = format_user_error(code, **kwargs)
        # Check for emoji at start (handle Unicode variations)
        emojis = ["❌", "⚠️", "⚠", "✅"]
        has_emoji = any(emoji in result[:3] for emoji in emojis)
        assert has_emoji, (
            f"Error message for {code} doesn't start with emoji: {result[:10]}"
        )

    def test_success_messages(self):
        """Test success message formatting."""
        result = format_user_success("CLAIMED", channel_mention="#voice-1")
        assert "✅" in result
        assert "#voice-1" in result
        assert "claimed" in result.lower() or "own" in result.lower()

        result = format_user_success(
            "TRANSFERRED", user_mention="@John", channel_mention="#voice-1"
        )
        assert "✅" in result
        assert "@John" in result
        assert "#voice-1" in result
