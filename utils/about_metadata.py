"""
Centralized About metadata for the TEST Clanker Discord bot.

Hardcoded strings are kept here to avoid scattering text across commands/embeds.
Update these values during your release workflow.
"""

BOT_NAME = "TEST Clanker"
BOT_VERSION = "v1.0.0"

BOT_DESCRIPTION = (
    "TEST Clanker powers automated verification, role management, "
    "voice channel tools, moderation utilities, and other features that keep your "
    "Discord community running smoothly. It provides reliable, scalable automation "
    "for leadership and members."
)

BOT_PURPOSE_ITEMS = [
    "Automated verification and membership management",
    "Role synchronization and enforcement",
    "Join-to-Create (JTC) voice channel creation and permissions",
    "Moderation utilities and audit logging",
    "Quality-of-life tools for administrators and members",
]

PRIVACY_SUMMARY = (
    "We collect only the data required to operate the bot: Discord user ID, username, and "
    "avatar; RSI handle and membership status; voice channel ownership/settings; activity "
    "metrics (message counts, voice/game session durations, aggregated analytics); and "
    "moderation/operational logs. We do not store message content. Data is used solely to run "
    "TEST Squadron automation and is not sold. Processing is based on Legitimate Interests "
    "under GDPR Article 6(1)(f), with retention limits (metrics default: 90 days)."
)

USER_RIGHTS_SUMMARY = (
    "Users may request copies of their data, correction of inaccuracies, deletion (Right to "
    "Erasure), or restriction/objection to processing. All requests are handled manually "
    "through our support system."
)

PRIVACY_REQUEST_STEPS = [
    "Open a support ticket in Discord and state 'privacy request'.",
    "Specify request type: access, correction, deletion, or objection/restriction.",
    "Staff will verify account ownership before processing.",
    "Target handling time is within 30 days.",
]

DATA_RETENTION_SUMMARY = (
    "Metrics retention defaults to 90 days (configurable). Operational logs are "
    "retained for short operational windows unless needed for active investigations."
)

LEGAL_BASIS_SUMMARY = (
    "Processing basis: Legitimate Interests (GDPR Article 6(1)(f)) for community "
    "verification, moderation, and automation."
)

SUPPORT_EMAIL = "Chromeninja@test.gg"
SUPPORT_TICKET_INFO = "Open a support ticket through the ticketing system in Discord."

PRIVACY_POLICY_URL = (
    "https://github.com/Chromeninja/test_squadron_discord_bot/blob/main/PRIVACY.md"
)
