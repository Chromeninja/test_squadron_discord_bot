"""
Centralized verification message templates for org-agnostic deployments.

This module provides:
- OrgBranding dataclass for org configuration
- get_org_branding() to fetch guild's org settings
- build_verification_text() for status-based welcome messages
- validate_verification_config() for early validation

All templates use Unicode emojis for portability across guilds.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from services.config_service import (
    CONFIG_ORG_LOGO_URL,
    CONFIG_ORG_NAME,
    CONFIG_ORG_SID,
    CONFIG_VERIFICATION_CHANNEL,
)
from utils.logging import get_logger

if TYPE_CHECKING:
    from bot import MyBot

logger = get_logger(__name__)


# ----------------------------------------------------------------------------- 
# Bot Identity Constant
# -----------------------------------------------------------------------------

BOT_DISPLAY_NAME = "TEST Clanker"


# -----------------------------------------------------------------------------
# Status Constants (prevent typos in string comparisons)
# -----------------------------------------------------------------------------

STATUS_MAIN = "main"
STATUS_AFFILIATE = "affiliate"
STATUS_NON_MEMBER = "non_member"

# Event type constants (for announcements)
EVENT_JOINED_MAIN = "joined_main"
EVENT_JOINED_AFFILIATE = "joined_affiliate"
EVENT_PROMOTED_TO_MAIN = "promoted_to_main"


# -----------------------------------------------------------------------------
# Message Fragment Constants (DRY for repeated copy)
# -----------------------------------------------------------------------------

_MSG_ENGAGE = (
    "Join our voice chats, explore events, and engage in our text channels"
)
_MSG_NICKNAME = "We set your Discord nickname to your RSI handle."
_MSG_FLY_SAFE = "\U0001fae1 Fly safe!"  # 🫡


# -----------------------------------------------------------------------------
# Organization Branding
# -----------------------------------------------------------------------------


@dataclass
class OrgBranding:
    """Organization branding configuration for a guild."""

    name: str
    sid: str
    logo_url: str | None = None

    @property
    def rsi_join_url(self) -> str:
        """RSI organization join URL derived from SID."""
        return f"https://robertsspaceindustries.com/orgs/{self.sid}"


async def get_org_branding(bot: "MyBot", guild_id: int) -> OrgBranding | None:
    """
    Fetch organization branding for a guild.

    Args:
        bot: Bot instance with config service
        guild_id: Guild ID for config lookup

    Returns:
        OrgBranding if org is configured, None otherwise
    """
    if not hasattr(bot, "services") or not hasattr(bot.services, "guild_config"):
        return None

    try:
        guild_config = bot.services.guild_config

        # Fetch org settings using centralized config keys
        org_name = await guild_config.get_setting(guild_id, CONFIG_ORG_NAME, default=None)
        org_sid = await guild_config.get_setting(guild_id, CONFIG_ORG_SID, default=None)

        if not org_name or not org_sid:
            return None

        # Clean up values
        org_name = org_name.strip() if isinstance(org_name, str) else None
        org_sid = org_sid.strip().upper() if isinstance(org_sid, str) else None

        if not org_name or not org_sid:
            return None

        # Optional: logo URL (defaults to None)
        logo_url = await guild_config.get_setting(
            guild_id, CONFIG_ORG_LOGO_URL, default=None
        )

        return OrgBranding(
            name=org_name,
            sid=org_sid,
            logo_url=logo_url,
        )

    except Exception as e:
        logger.warning(
            f"Failed to fetch org branding for guild {guild_id}: {e}",
            extra={"guild_id": guild_id},
        )
        return None


# -----------------------------------------------------------------------------
# Validation
# -----------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """Result of verification configuration validation."""

    ok: bool
    reason: str | None = None


async def validate_verification_config(bot: "MyBot", guild_id: int) -> ValidationResult:
    """
    Validate that verification is properly configured for a guild.

    Checks:
    - organization.name is set
    - organization.sid is set
    - verification channel is configured

    Args:
        bot: Bot instance with config service
        guild_id: Guild ID to validate

    Returns:
        ValidationResult with ok=True if configured, or ok=False with reason
    """
    if not hasattr(bot, "services") or not hasattr(bot.services, "guild_config"):
        return ValidationResult(ok=False, reason="Configuration service not available")

    try:
        guild_config = bot.services.guild_config

        # Check org name
        org_name = await guild_config.get_setting(guild_id, CONFIG_ORG_NAME, default=None)
        if not org_name or not str(org_name).strip():
            return ValidationResult(
                ok=False,
                reason="Organization name not configured. Set `organization.name` in guild settings.",
            )

        # Check org SID
        org_sid = await guild_config.get_setting(guild_id, CONFIG_ORG_SID, default=None)
        if not org_sid or not str(org_sid).strip():
            return ValidationResult(
                ok=False,
                reason="Organization SID not configured. Set `organization.sid` in guild settings.",
            )

        # Check verification channel
        verification_channel = await guild_config.get_setting(
            guild_id, CONFIG_VERIFICATION_CHANNEL, default=None
        )
        if not verification_channel:
            return ValidationResult(
                ok=False,
                reason="Verification channel not configured. Set `channels.verification_channel_id` in guild settings.",
            )

        return ValidationResult(ok=True)

    except Exception as e:
        logger.warning(f"Failed to validate verification config for guild {guild_id}: {e}")
        return ValidationResult(ok=False, reason="Failed to validate configuration")


# -----------------------------------------------------------------------------
# Message Templates
# -----------------------------------------------------------------------------


def build_verification_text(org: OrgBranding, status: str) -> str:
    """
    Build verification success message based on membership status.

    Uses Unicode emojis for portability. Messages are neutral and informational.

    Args:
        org: Organization branding configuration
        status: Membership status (STATUS_MAIN, STATUS_AFFILIATE, STATUS_NON_MEMBER)

    Returns:
        Formatted verification message string
    """
    if status == STATUS_MAIN:
        return (
            f"\U0001f389 **Welcome to {org.name}!**\n\n"
            f"You're verified as a **Main** member of **{org.name}**.\n\n"
            f"{_MSG_ENGAGE} to make the most of your experience!\n\n"
            f"{_MSG_FLY_SAFE}\n\n"
            f"{_MSG_NICKNAME}"
        )

    elif status == STATUS_AFFILIATE:
        return (
            f"\U0001f389 **Welcome to {org.name}!**\n\n"
            f"You're verified as an **Affiliate** member of **{org.name}**.\n\n"
            f"Consider setting **{org.sid}** as your Main Org:\n"
            ":point_right: [Change Your Main Org](https://robertsspaceindustries.com/account/organization)\n"
            f"Click **Set as Main** next to **{org.name}**.\n\n"
            f"{_MSG_ENGAGE}!\n\n"
            f"{_MSG_FLY_SAFE}\n\n"
            f"{_MSG_NICKNAME}"
        )

    elif status == STATUS_NON_MEMBER:
        return (
            "\U0001f44b **Welcome!**\n\n"
            f"It looks like you're not yet a member of **{org.name}**.\n\n"
            f"\U0001f517 [Join {org.name}]({org.rsi_join_url})\n"
            "Click **Enlist Now!** Membership requests are usually approved within "
            "24-72 hours. Reverify after approval to update your roles.\n\n"
            "In the meantime, join our voice chats and text channels!\n\n"
            f"{_MSG_NICKNAME}"
        )

    else:
        return (
            "Welcome to the server! You can verify again after 3 hours if needed.\n\n"
            f"{_MSG_NICKNAME}"
        )


def build_announcement_footer(org: OrgBranding, event_type: str) -> str:
    """
    Build neutral announcement footer based on event type.

    Args:
        org: Organization branding configuration
        event_type: Event type (EVENT_JOINED_MAIN, EVENT_JOINED_AFFILIATE, EVENT_PROMOTED_TO_MAIN)

    Returns:
        Neutral footer message string
    """
    if event_type == EVENT_JOINED_MAIN:
        return f"Welcome to {org.name}!"

    elif event_type == EVENT_JOINED_AFFILIATE:
        return (
            f"Welcome aboard! Consider setting {org.sid} as your **Main Org** "
            "to fully join."
        )

    elif event_type == EVENT_PROMOTED_TO_MAIN:
        return f"{_MSG_FLY_SAFE.split()[0]} Welcome fully to {org.name}!"

    else:
        return f"Welcome to {org.name}!"
