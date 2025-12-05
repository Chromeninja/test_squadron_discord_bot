import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Literal

import discord  # legacy (embeds no longer dispatched)

from helpers.discord_api import channel_send_message
from utils.logging import get_logger

logger = get_logger(__name__)


class EventType(str, Enum):
    VERIFICATION = "VERIFICATION"  # User initial verification ("User Verify")
    RECHECK = "RECHECK"  # User initiated re-check via button
    AUTO_CHECK = "AUTO_CHECK"  # Scheduled automatic re-check
    ADMIN_CHECK = "ADMIN_CHECK"  # Admin initiated manual check


@dataclass
class ChangeSet:
    user_id: int
    event: EventType
    initiator_kind: Literal["User", "Admin", "Auto"]
    initiator_name: str | None = None
    guild_id: int | None = None  # Guild where the event occurred

    status_before: str | None = None
    status_after: str | None = None
    moniker_before: str | None = None
    moniker_after: str | None = None
    handle_before: str | None = None
    handle_after: str | None = None
    username_before: str | None = None
    username_after: str | None = None

    # Organization changes
    main_orgs_before: list[str] | None = None
    main_orgs_after: list[str] | None = None
    affiliate_orgs_before: list[str] | None = None
    affiliate_orgs_after: list[str] | None = None

    roles_added: list[str] = field(default_factory=list)  # ignored in new formatter
    roles_removed: list[str] = field(default_factory=list)  # ignored in new formatter

    notes: str | None = None
    # Use timezone-aware UTC now instead of deprecated utcnow() for future-proofing
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    duration_ms: int = 0


MD_ESCAPE_CHARS = ["`", "*", "_", "~", "|", ">", "\\"]

# In‑memory short window dedupe store: (user_id, signature) -> last_post_ts
_DEDUP_CACHE: dict[tuple[int, str], float] = {}
_DEDUP_TTL_SECONDS = 20  # within 20s identical change suppressed


def escape_md(value: str) -> str:
    if value is None:
        return ""
    out = []
    for ch in value:
        if ch in MD_ESCAPE_CHARS:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return f"`{''.join(out)}`"


def _changed(a: str | None, b: str | None) -> bool:
    return (a or "") != (b or "")


def _changed_case_sensitive(a: str | None, b: str | None) -> bool:
    """Case sensitive change check used for rendering sections.
    Noise suppression (case only) handled in higher-level suppression logic."""
    return (a or "") != (b or "")


def _changed_material(a: str | None, b: str | None) -> bool:
    """Material textual change ignoring case only differences."""
    return (a or "").lower() != (b or "").lower()


async def _managed_role_names(bot, guild_id: int) -> list[str]:
    """Get names of managed verification roles for a guild."""
    names = []

    if not hasattr(bot, "services") or not bot.services:
        return names

    try:
        role_keys = [
            "roles.bot_verified_role",
            "roles.main_role",
            "roles.affiliate_role",
            "roles.nonmember_role",
        ]

        for role_key in role_keys:
            role_ids = await bot.services.config.get_guild_setting(
                guild_id, role_key, []
            )
            if role_ids:
                role_id = role_ids[0]  # Get first role from list
                role = bot.role_cache.get(role_id)
                if role:
                    names.append(role.name)
    except Exception:
        pass

    return names


def _material_textual_changed_all(cs: ChangeSet) -> bool:
    """Return True if any material (case-insensitive) textual field changed.

    Covers status, moniker, handle, username for suppression logic. Extracted
    to satisfy code-quality suggestion (extract-method) and improve clarity.
    """
    return any(
        [
            _changed_material(cs.status_before, cs.status_after),
            _changed_material(cs.moniker_before, cs.moniker_after),
            _changed_material(cs.handle_before, cs.handle_after),
            _changed_material(cs.username_before, cs.username_after),
        ]
    )


def is_effectively_unchanged(cs: ChangeSet, bot=None) -> bool:
    """Return True when there is no material change to report.

    Suppress:
      - Case-only moniker / nickname / handle changes
      - Pure role order permutations (we only consider managed role set + added/removed lists)
      - Non-managed role churn (we filter roles before populating ChangeSet)
    Always post if notes contain error/404/override semantics.
    """
    if cs.notes:
        lower = cs.notes.lower()
        if any(k in lower for k in ["error", "fail", "404", "override"]):
            return False

    # Material textual changes (case-insensitive)
    textual = _material_textual_changed_all(cs)

    role_diff = bool(cs.roles_added or cs.roles_removed)
    # If only case differences, treat as unchanged.
    return not textual and not role_diff


def color_for(cs: ChangeSet) -> int:
    # Discord color ints (approx): green, yellow, red, blurple
    GREEN = 0x2ECC71
    YELLOW = 0xF1C40F
    RED = 0xE74C3C
    BLURPLE = 0x5865F2

    if cs.notes and any(k in cs.notes.lower() for k in ["error", "fail", "404"]):
        return RED

    if _changed(cs.status_before, cs.status_after):
        # Promotion/demotion (database format: main, affiliate, non_member)
        after = (cs.status_after or "").lower()
        before = (cs.status_before or "").lower()
        verified_set = {"main", "affiliate"}
        if after in verified_set and before not in verified_set:
            return GREEN
        if after == "non_member" and before in verified_set:
            return RED
        return YELLOW

    if cs.roles_added and not cs.roles_removed:
        return GREEN
    if cs.roles_removed and not cs.roles_added:
        return YELLOW
    if cs.roles_added or cs.roles_removed:
        return YELLOW

    # Only moniker/handle changes => informational
    if _changed(cs.moniker_before, cs.moniker_after) or _changed(
        cs.handle_before, cs.handle_after
    ):
        return BLURPLE

    return BLURPLE


def _event_title(ev: EventType) -> str:
    return {
        EventType.VERIFICATION: "Verification",
        EventType.RECHECK: "Recheck",
        EventType.AUTO_CHECK: "Auto Check",
        EventType.ADMIN_CHECK: "Admin Check",
    }.get(ev, ev.value)


def build_message(bot, cs: ChangeSet) -> str:
    """Public helper returning current plain-text representation."""
    return _render_plaintext(cs)


def _event_emoji(cs: ChangeSet) -> str:
    if cs.notes and cs.notes and "404" in cs.notes.lower():
        return "⚠️"
    return {
        EventType.ADMIN_CHECK: "🧑‍✈️",
        EventType.VERIFICATION: "✅",
        EventType.RECHECK: "🔁",
        EventType.AUTO_CHECK: "🤖",
    }.get(cs.event, "🗂️")


async def _verbosity(bot) -> str:
    """Get leadership log verbosity from config service."""
    try:
        if hasattr(bot, "services") and bot.services:
            return await bot.services.config.get_global_setting(
                "leadership_log.verbosity", "normal"
            )
        return "normal"
    except Exception as e:
        logger.debug(f"Failed to get leadership log verbosity: {e}")
        return "normal"


def _normalize_signature(cs: ChangeSet) -> str:
    parts = [
        cs.status_before or "",
        cs.status_after or "",
        (cs.moniker_before or "").lower(),
        (cs.moniker_after or "").lower(),
        (cs.handle_before or "").lower(),
        (cs.handle_after or "").lower(),
        (cs.username_before or "").lower(),
        (cs.username_after or "").lower(),
        "|".join(sorted([r.lower() for r in cs.roles_added])) if cs.roles_added else "",
        (
            "|".join(sorted([r.lower() for r in cs.roles_removed]))
            if cs.roles_removed
            else ""
        ),
        (cs.notes or "").lower(),
        cs.event.value,
    ]
    return "§".join(parts)


def build_embed(bot, cs: ChangeSet) -> discord.Embed:
    """Create the structured leadership log embed per specification."""
    emoji = _event_emoji(cs)
    duration = ""  # duration tracking removed
    title = f"🗂️ <@{cs.user_id}> — Verification Update"
    header_initiated = f"Initiated by {cs.initiator_kind}" + (
        f" ({cs.initiator_name})"
        if cs.initiator_kind == "Admin" and cs.initiator_name
        else ""
    )
    embed = discord.Embed(title=title, color=color_for(cs))
    embed.description = (
        f"{emoji} {_event_title(cs.event)} • {header_initiated}{duration}"
    )

    def add_section(label: str, before: str | None, after: str | None):
        if _changed_material(before, after):
            embed.add_field(
                name=label, value=f"{before or '—'} → {after or '—'}", inline=False
            )
        elif _verbosity(bot) == "verbose":
            # In verbose mode show unchanged chips
            if before:
                embed.add_field(name=label, value=f"No Change ({before})", inline=False)

    add_section("Membership Status", cs.status_before, cs.status_after)
    # Updated labels (Aug 2025 policy): concise field names
    add_section("Handle", cs.handle_before, cs.handle_after)
    add_section("Moniker", cs.moniker_before, cs.moniker_after)
    add_section("Username", cs.username_before, cs.username_after)

    # Organization changes with suppression logic
    main_orgs_changed = _orgs_changed(cs.main_orgs_before, cs.main_orgs_after)
    if main_orgs_changed and not _suppress_org_change(
        cs.main_orgs_before, cs.main_orgs_after, cs.event
    ):
        embed.add_field(
            name="Main Organization",
            value=f"{_format_org_list(cs.main_orgs_before)} → {_format_org_list(cs.main_orgs_after)}",
            inline=False,
        )

    affiliate_orgs_changed = _orgs_changed(
        cs.affiliate_orgs_before, cs.affiliate_orgs_after
    )
    if affiliate_orgs_changed and not _suppress_org_change(
        cs.affiliate_orgs_before, cs.affiliate_orgs_after, cs.event
    ):
        embed.add_field(
            name="Affiliate Organizations",
            value=f"{_format_org_list(cs.affiliate_orgs_before)} → {_format_org_list(cs.affiliate_orgs_after)}",
            inline=False,
        )

    if cs.roles_added:
        embed.add_field(
            name="Roles Added",
            value="\n".join(f"• {r}" for r in cs.roles_added),
            inline=False,
        )
    if cs.roles_removed:
        embed.add_field(
            name="Roles Removed",
            value="\n".join(f"• {r}" for r in cs.roles_removed),
            inline=False,
        )

    if cs.notes:
        embed.add_field(name="Notes", value=cs.notes, inline=False)

    # Footer
    handle = cs.handle_after or cs.handle_before or "No Handle"
    # Use ChangeSet.started_at (when processing began) for consistent timing; fallback to current UTC
    try:
        started_at = getattr(cs, "started_at", None)
        if started_at:
            if getattr(started_at, "tzinfo", None) is None:
                started_at = started_at.replace(tzinfo=UTC)
            else:
                started_at = started_at.astimezone(UTC)
            timestamp = started_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        else:
            timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        timestamp = "Unknown"
    footer_text = f"{cs.user_id} • {handle} • {timestamp}"
    if handle and handle != "No Handle":
        try:
            embed.url = f"https://robertsspaceindustries.com/citizens/{handle}"
        except Exception:  # pragma: no cover
            pass
    embed.set_footer(text=footer_text)
    return embed


def _truncate(value: str | None, length: int = 32) -> str | None:
    if value is None:
        return None
    v = value.strip()
    return v if len(v) <= length else f"{v[: length - 1]}…"


_MD_INLINE = {"`", "*", "_", "~", "|", ">"}


def _escape_inline(value: str | None) -> str:
    if value is None:
        return ""
    out = []
    for ch in value:
        if ch in _MD_INLINE:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def _header_tag(cs: ChangeSet) -> str:
    if cs.event == EventType.VERIFICATION:
        return "Verification • User"
    if cs.event == EventType.RECHECK and cs.initiator_kind == "User":
        return "Recheck • User"
    if cs.event == EventType.ADMIN_CHECK:
        suffix = (
            f" • Admin: {cs.initiator_name}"
            if cs.initiator_kind == "Admin" and cs.initiator_name
            else ""
        )
        return f"Admin Check{suffix}"
    return "Auto Check" if cs.event == EventType.AUTO_CHECK else cs.event.name


def _outcome(cs: ChangeSet, has_changes: bool) -> tuple[str, str]:
    if not has_changes:
        return ("No changes", "🥺")
    if cs.event == EventType.VERIFICATION:
        return ("Verified", "✅")
    return ("Updated", "🔁")


def _build_header(cs: ChangeSet, has_changes: bool) -> str:
    tag = _header_tag(cs)
    outcome, emoji = _outcome(cs, has_changes)
    return f"[{tag}] <@{cs.user_id}> {emoji} {outcome}"


def _format_duration(ms: int) -> str:  # legacy stub (kept for compatibility)
    return ""


def _field_label_map() -> dict:  # legacy
    return {}


def _format_value(val: str | None) -> str:
    """Escape markdown then quote if the original (unescaped) contains spaces or non-alphanumerics.

    (none) marker is preserved unquoted. Empty string becomes "".
    """
    if val is None:
        return "(none)"
    original = val
    if original == "":
        return '""'
    import re

    needs_quote = not re.match(r"^[A-Za-z0-9_]+$", original)
    escaped = _escape_inline(original)
    return f'"{escaped}"' if needs_quote else escaped


def _orgs_changed(before: list[str] | None, after: list[str] | None) -> bool:
    """Check if organization lists changed (ignoring REDACTED)."""
    # Filter out REDACTED entries for comparison
    before_filtered = {sid for sid in (before or []) if sid != "REDACTED"}
    after_filtered = {sid for sid in (after or []) if sid != "REDACTED"}
    return before_filtered != after_filtered


def _format_org_list(orgs: list[str] | None) -> str:
    """Format organization list for display, with REDACTED count."""
    if not orgs:
        return "(none)"
    visible = [sid for sid in orgs if sid != "REDACTED"]
    redacted_count = len([sid for sid in orgs if sid == "REDACTED"])

    if not visible and redacted_count > 0:
        return f"[{redacted_count} hidden]"
    elif visible and redacted_count > 0:
        return f"{', '.join(visible)} (+{redacted_count} hidden)"
    elif visible:
        return ", ".join(visible)
    else:
        return "(none)"


def _suppress_org_change(
    before: list[str] | None, after: list[str] | None, event: EventType
) -> bool:
    """Determine if org change should be suppressed (null to populated during auto-check)."""
    # Suppress if transitioning from null/empty to populated during auto-checks (initial backfill)
    if event == EventType.AUTO_CHECK:
        before_empty = not before or len(before) == 0
        after_populated = after and len(after) > 0
        if before_empty and after_populated:
            return True
    return False


def _render_plaintext(cs: ChangeSet) -> str:
    status_changed = _changed_material(cs.status_before, cs.status_after)
    moniker_changed = _changed_material(cs.moniker_before, cs.moniker_after)
    # Suppress initial moniker population during auto checks (noise when feature rolled out)
    if moniker_changed and cs.event == EventType.AUTO_CHECK:
        before = (cs.moniker_before or "").strip().lower()
        if before in {"", "(none)", "none"}:
            moniker_changed = False
    username_changed = _changed_material(cs.username_before, cs.username_after)
    handle_changed = _changed_material(cs.handle_before, cs.handle_after)

    # Check org changes
    main_orgs_changed = _orgs_changed(cs.main_orgs_before, cs.main_orgs_after)
    affiliate_orgs_changed = _orgs_changed(
        cs.affiliate_orgs_before, cs.affiliate_orgs_after
    )

    # Suppress org changes if transitioning from null to populated during auto-check
    if main_orgs_changed and _suppress_org_change(
        cs.main_orgs_before, cs.main_orgs_after, cs.event
    ):
        main_orgs_changed = False
    if affiliate_orgs_changed and _suppress_org_change(
        cs.affiliate_orgs_before, cs.affiliate_orgs_after, cs.event
    ):
        affiliate_orgs_changed = False

    has_changes = (
        status_changed
        or moniker_changed
        or username_changed
        or handle_changed
        or main_orgs_changed
        or affiliate_orgs_changed
    )
    header = _build_header(cs, has_changes)
    if not has_changes:
        return header
    lines = [header]
    if status_changed:
        lines.append(
            f"Status: {_format_value(_truncate(cs.status_before or ''))} → {_format_value(_truncate(cs.status_after or ''))}"
        )
    if moniker_changed:
        lines.append(
            f"Moniker: {_format_value(_truncate(cs.moniker_before or '(none)'))} → {_format_value(_truncate(cs.moniker_after or '(none)'))}"
        )
    if username_changed:
        lines.append(
            f"Username: {_format_value(_truncate(cs.username_before or '(none)'))} → {_format_value(_truncate(cs.username_after or '(none)'))}"
        )
    if handle_changed:
        lines.append(
            f"Handle: {_format_value(_truncate(cs.handle_before or '(none)'))} → {_format_value(_truncate(cs.handle_after or '(none)'))}"
        )
    if main_orgs_changed:
        lines.append(
            f"Main Org: {_format_org_list(cs.main_orgs_before)} → {_format_org_list(cs.main_orgs_after)}"
        )
    if affiliate_orgs_changed:
        lines.append(
            f"Affiliate Orgs: {_format_org_list(cs.affiliate_orgs_before)} → {_format_org_list(cs.affiliate_orgs_after)}"
        )
    return "\n".join(lines)


async def post_if_changed(bot, cs: ChangeSet):
    # Normalize roles to managed set only; discard others for change signature & rendering
    if not cs.guild_id:
        return  # Cannot proceed without guild context

    managed_names = set(await _managed_role_names(bot, cs.guild_id))
    if cs.roles_added:
        cs.roles_added = [r for r in cs.roles_added if r in managed_names]
    if cs.roles_removed:
        cs.roles_removed = [r for r in cs.roles_removed if r in managed_names]

    # Filter out case-only changes by rewriting after values to before when only case differs.
    # Central list of tracked textual attributes for easier maintenance.
    CHANGE_ATTRS = ("moniker", "username", "handle")
    for attr in CHANGE_ATTRS:
        before = getattr(cs, f"{attr}_before")
        after = getattr(cs, f"{attr}_after")
        if before and after and before.lower() == after.lower() and before != after:
            setattr(cs, f"{attr}_after", before)  # revert to suppress

    status_changed = _changed_material(cs.status_before, cs.status_after)
    moniker_changed = _changed_material(cs.moniker_before, cs.moniker_after)
    if moniker_changed and cs.event == EventType.AUTO_CHECK:
        before = (cs.moniker_before or "").strip().lower()
        if before in {"", "(none)", "none"}:
            moniker_changed = False
    username_changed = _changed_material(cs.username_before, cs.username_after)
    handle_changed = _changed_material(cs.handle_before, cs.handle_after)

    # Check org changes with suppression
    main_orgs_changed = _orgs_changed(cs.main_orgs_before, cs.main_orgs_after)
    if main_orgs_changed and _suppress_org_change(
        cs.main_orgs_before, cs.main_orgs_after, cs.event
    ):
        main_orgs_changed = False

    affiliate_orgs_changed = _orgs_changed(
        cs.affiliate_orgs_before, cs.affiliate_orgs_after
    )
    if affiliate_orgs_changed and _suppress_org_change(
        cs.affiliate_orgs_before, cs.affiliate_orgs_after, cs.event
    ):
        affiliate_orgs_changed = False

    has_changes = (
        status_changed
        or moniker_changed
        or username_changed
        or handle_changed
        or main_orgs_changed
        or affiliate_orgs_changed
    )
    if cs.event == EventType.AUTO_CHECK and not has_changes:
        return  # suppress entirely for auto no-change

    # Dedupe short window
    sig = _normalize_signature(cs)
    key = (cs.user_id, sig)
    now = time.time()
    # Purge expired keys opportunistically
    if len(_DEDUP_CACHE) > 1000:  # safety bound
        expired = [k for k, v in _DEDUP_CACHE.items() if now - v > _DEDUP_TTL_SECONDS]
        for k in expired:
            _DEDUP_CACHE.pop(k, None)
    last = _DEDUP_CACHE.get(key)
    if last and now - last < _DEDUP_TTL_SECONDS:
        logger.debug("Leadership log deduped identical ChangeSet within window.")
        return
    _DEDUP_CACHE[key] = now

    # Channel resolution via config service
    channel = None
    try:
        if hasattr(bot, "services") and bot.services:
            # Use guild_id from changeset if available, otherwise fall back to first guild
            guild_id = (
                cs.guild_id
                if cs.guild_id
                else (bot.guilds[0].id if bot.guilds else None)
            )
            if guild_id:
                guild_config = bot.services.guild_config
                # Try to get the guild object
                guild = bot.get_guild(guild_id)
                if guild:
                    channel = await guild_config.get_channel(
                        guild_id, "leadership_announcement_channel_id", guild
                    )

        # Fallback to legacy attribute if config service unavailable
        if not channel and hasattr(bot, "LEADERSHIP_LOG_CHANNEL_ID"):
            channel_id = bot.LEADERSHIP_LOG_CHANNEL_ID
            if channel_id:
                channel = bot.get_channel(int(channel_id))

    except Exception as e:
        logger.debug(f"Failed to resolve leadership log channel: {e}")
        # Try legacy fallback
        channel_id = getattr(bot, "LEADERSHIP_LOG_CHANNEL_ID", None)
        if channel_id:
            channel = bot.get_channel(int(channel_id))

    if not channel:
        logger.debug(
            "Leadership log channel not configured or not found; skipping post."
        )
        return
    try:
        content = _render_plaintext(cs)
        await channel_send_message(channel, content, embed=None)  # plain text only now
    except Exception as e:
        logger.warning(f"Failed posting leadership log: {e}")


__all__ = [
    "ChangeSet",
    "EventType",
    "build_embed",  # build_embed retained for backwards compatibility (may be removed later)
    "build_message",
    "color_for",
    "escape_md",
    "is_effectively_unchanged",
    "post_if_changed",
]
