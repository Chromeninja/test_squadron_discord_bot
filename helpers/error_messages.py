"""
Centralized error message formatting for user-facing Discord errors.

This module provides consistent, user-friendly error messages for the TEST Clanker
voice feature. All error messages are short, actionable, and never expose internal
technical details to users.

Format: emoji + **Bold Title** + newline + actionable body (≤120 chars total)
"""

from utils.logging import get_logger

logger = get_logger(__name__)


def format_user_error(code: str, **kwargs) -> str:
    """
    Format a user-friendly error message based on an error code.

    All returned messages are designed to be:
    - Short (<120 characters total)
    - Formatted as: emoji + **Bold Title** + \\n + actionable sentence
    - Actionable (tell users what to do)
    - Consistent in tone and style
    - Never expose technical details

    Args:
        code: Error code identifying the type of error
        **kwargs: Dynamic values to insert into error messages
            - owner_display: Display name of the current owner (for OWNER_PRESENT)
            - seconds: Cooldown duration in seconds (for COOLDOWN)

    Returns:
        User-friendly error message string

    Examples:
        >>> format_user_error("OWNER_PRESENT")
        "❌ You can't claim this channel while the current owner is still present."

        >>> format_user_error("COOLDOWN", seconds=5)
        "⚠️ **Slow down**\\nPlease wait 5s between channel creations."

        >>> format_user_error("NOT_IN_VOICE")
        "❌ **Not in voice**\\nJoin the voice channel you want to manage first."
    """
    error_messages = {
        "OWNER_PRESENT": "❌ You can't claim this channel while the current owner is still present.",
        "NOT_IN_VOICE": "❌ **Not in voice**\nJoin the voice channel you want to manage first.",
        "NOT_OWNER": "❌ **Not your channel**\nOnly the channel owner can do that.",
        "NOT_MANAGED": "❌ **Not a managed channel**\nThis channel isn't managed by TEST Clanker.",
        "COOLDOWN": "⚠️ **Slow down**\nPlease wait {seconds}s between channel creations.",
        "DB_TEMP_ERROR": "❌ **Temporary issue**\nDatabase hiccup. Please try again in a moment.",
        "PERMISSION": "❌ You don't have permission to use this command.",
        "UNKNOWN": "❌ **Something went wrong**\nAn unexpected error occurred. The issue was logged.",
        "NO_CHANNEL": "❌ **No active channel**\nYou don't have an active voice channel right now.",
        "NOT_IN_CHANNEL": "❌ **User not present**\nThe new owner must be in your voice channel.",
        "NO_JTC_CONFIGURED": "❌ **System not set up**\nNo join-to-create channels are configured for this server.",
        "JTC_NOT_FOUND": "❌ **Setup issue**\nThe join-to-create channel wasn't found.",
        "CREATION_FAILED": "❌ **Creation failed**\nFailed to create voice channel. Please try again.",
    }

    # Log warning if unknown error code is used
    if code not in error_messages:
        logger.warning(f"Unknown error code used in format_user_error: {code}")

    message = error_messages.get(code, error_messages["UNKNOWN"])

    # Format message with provided kwargs
    try:
        return message.format(**kwargs)
    except KeyError as e:
        # If formatting fails due to missing kwargs, return the unformatted message
        # This is a safety fallback - in production this should not happen
        return message.replace("{" + str(e).strip("'") + "}", "???")


def format_user_success(code: str, **kwargs) -> str:
    """
    Format a user-friendly success message based on a success code.

    Format: ✅ + **Bold Title** + \\n + confirmation sentence

    Args:
        code: Success code identifying the type of success
        **kwargs: Dynamic values to insert into success messages
            - channel_mention: Channel mention (for voice operations)
            - user_mention: User mention (for transfers)

    Returns:
        User-friendly success message string

    Examples:
        >>> format_user_success("CLAIMED", channel_mention="#voice-1")
        "✅ **Channel claimed**\\nYou now own #voice-1."

        >>> format_user_success("TRANSFERRED", user_mention="@John", channel_mention="#voice-1")
        "✅ **Ownership transferred**\\n@John now owns #voice-1."
    """
    success_messages = {
        "CLAIMED": "✅ **Channel claimed**\nYou now own {channel_mention}.",
        "TRANSFERRED": "✅ **Ownership transferred**\n{user_mention} now owns {channel_mention}.",
        "CREATED": "✅ **Channel created**\nWelcome to {channel_mention}!",
        "SETUP_COMPLETE": "✅ **Setup complete**\nVoice system is ready to use.",
    }

    message = success_messages.get(code, "✅ **Success**\nOperation completed.")

    # Format message with provided kwargs
    try:
        return message.format(**kwargs)
    except KeyError:
        # If formatting fails, return generic success
        return "✅ **Success**\nOperation completed."
