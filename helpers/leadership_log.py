from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
from typing import List, Optional, Literal, Tuple, Dict
import time

import discord  # NOTE: legacy embed support retained for backward compat in older tests; new flow uses plain text

from helpers.logger import get_logger
from helpers.discord_api import channel_send_message

logger = get_logger(__name__)


class EventType(str, Enum):
    VERIFICATION = "VERIFICATION"  # User initial verification ("User Verify")
    RECHECK = "RECHECK"            # User initiated re-check via button
    AUTO_CHECK = "AUTO_CHECK"      # Scheduled automatic re-check
    ADMIN_CHECK = "ADMIN_CHECK"    # Admin initiated manual check


@dataclass
class ChangeSet:
    user_id: int
    event: EventType
    initiator_kind: Literal['User','Admin','Auto']
    initiator_name: Optional[str] = None

    status_before: Optional[str] = None
    status_after: Optional[str] = None
    moniker_before: Optional[str] = None
    moniker_after: Optional[str] = None
    handle_before: Optional[str] = None
    handle_after: Optional[str] = None
    username_before: Optional[str] = None
    username_after: Optional[str] = None

    roles_added: List[str] = field(default_factory=list)   # retained for compatibility but no longer rendered
    roles_removed: List[str] = field(default_factory=list) # retained for compatibility but no longer rendered

    notes: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    duration_ms: int = 0


MD_ESCAPE_CHARS = ['`', '*', '_', '~', '|', '>', '\\']

# In‑memory short window dedupe store: (user_id, signature) -> last_post_ts
_DEDUP_CACHE: Dict[Tuple[int, str], float] = {}
_DEDUP_TTL_SECONDS = 20  # within 20s identical change suppressed


def escape_md(value: str) -> str:
    if value is None:
        return ''
    out = []
    for ch in value:
        if ch in MD_ESCAPE_CHARS:
            out.append('\\' + ch)
        else:
            out.append(ch)
    return f"`{''.join(out)}`"


def _changed(a: Optional[str], b: Optional[str]) -> bool:
    return (a or '') != (b or '')


def _changed_case_sensitive(a: Optional[str], b: Optional[str]) -> bool:
    """Case sensitive change check used for rendering sections.
    Noise suppression (case only) handled in higher-level suppression logic."""
    return (a or '') != (b or '')


def _changed_material(a: Optional[str], b: Optional[str]) -> bool:
    """Material textual change ignoring case only differences."""
    return (a or '').lower() != (b or '').lower()


def _managed_role_names(bot) -> List[str]:  # pragma: no cover (trivial helper)
    names = []
    keys = [
        'BOT_VERIFIED_ROLE_ID',
        'MAIN_ROLE_ID',
        'AFFILIATE_ROLE_ID',
        'NON_MEMBER_ROLE_ID',
    ]
    for k in keys:
        rid = getattr(bot, k, None)
        if not rid:
            continue
        role = getattr(bot, 'role_cache', {}).get(rid)
        if role is None:
            # Attempt guild fetch fallback (first guild assumed)
            try:
                guild = bot.guilds[0]
                role = guild.get_role(rid)
            except Exception:
                role = None
        if role:
            names.append(getattr(role, 'name', str(role)))
    return names


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
    textual = any([
        _changed_material(cs.status_before, cs.status_after),
        _changed_material(cs.moniker_before, cs.moniker_after),
        _changed_material(cs.handle_before, cs.handle_after),
        _changed_material(cs.username_before, cs.username_after),
    ])

    role_diff = bool(cs.roles_added or cs.roles_removed)
    # If only case differences, treat as unchanged.
    if not textual and not role_diff:
        return True
    return False


def color_for(cs: ChangeSet) -> int:
    # Discord color ints (approx): green, yellow, red, blurple
    GREEN = 0x2ecc71
    YELLOW = 0xf1c40f
    RED = 0xe74c3c
    BLURPLE = 0x5865F2

    if cs.notes and any(k in cs.notes.lower() for k in ["error", "fail", "404"]):
        return RED

    if _changed(cs.status_before, cs.status_after):
        # Promotion/demotion (treat Main/Affiliate/Verified variants equivalently)
        after = (cs.status_after or '').lower()
        before = (cs.status_before or '').lower()
        verified_set = {'verified', 'main', 'affiliate'}
        if after in verified_set and before not in verified_set:
            return GREEN
        if after == 'not a member' and before in verified_set:
            return RED
        return YELLOW

    if cs.roles_added and not cs.roles_removed:
        return GREEN
    if cs.roles_removed and not cs.roles_added:
        return YELLOW
    if cs.roles_added or cs.roles_removed:
        return YELLOW

    # Only moniker/handle changes => informational
    if _changed(cs.moniker_before, cs.moniker_after) or _changed(cs.handle_before, cs.handle_after):
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
    """Return the new plain‑text leadership log message.

    This is the core renderer used by post_if_changed. It purposefully ignores the
    previously used embed layout while keeping a simplified interface so existing
    callers (tests) that invoked build_message still succeed.
    """
    return _render_plaintext(cs)


def _event_emoji(cs: ChangeSet) -> str:
    if cs.notes and cs.notes and '404' in cs.notes.lower():
        return '⚠️'
    return {
        EventType.ADMIN_CHECK: '🧑‍✈️',
        EventType.VERIFICATION: '✅',
        EventType.RECHECK: '🔁',
        EventType.AUTO_CHECK: '🤖',
    }.get(cs.event, '🗂️')


def _verbosity(bot) -> str:
    try:
        return ((bot.config or {}).get('leadership_log', {}) or {}).get('verbosity', 'normal').lower()
    except Exception:
        return 'normal'


def _normalize_signature(cs: ChangeSet) -> str:
    parts = [
        cs.status_before or '', cs.status_after or '',
        (cs.moniker_before or '').lower(), (cs.moniker_after or '').lower(),
        (cs.handle_before or '').lower(), (cs.handle_after or '').lower(),
        (cs.username_before or '').lower(), (cs.username_after or '').lower(),
        '|'.join(sorted([r.lower() for r in cs.roles_added])) if cs.roles_added else '',
        '|'.join(sorted([r.lower() for r in cs.roles_removed])) if cs.roles_removed else '',
        (cs.notes or '').lower(),
        cs.event.value,
    ]
    return '§'.join(parts)


def build_embed(bot, cs: ChangeSet) -> discord.Embed:
    """Create the structured leadership log embed per specification."""
    emoji = _event_emoji(cs)
    duration = ''  # duration tracking removed
    title = f"🗂️ <@{cs.user_id}> — Verification Update"
    header_initiated = f"Initiated by {cs.initiator_kind}" + (f" ({cs.initiator_name})" if cs.initiator_kind == 'Admin' and cs.initiator_name else '')
    embed = discord.Embed(title=title, color=color_for(cs))
    embed.description = f"{emoji} {_event_title(cs.event)} • {header_initiated}{duration}"

    def add_section(label: str, before: Optional[str], after: Optional[str]):
        if _changed_material(before, after):
            embed.add_field(name=label, value=f"{before or '—'} → {after or '—'}", inline=False)
        elif _verbosity(bot) == 'verbose':
            # In verbose mode show unchanged chips
            if before:
                embed.add_field(name=label, value=f"No Change ({before})", inline=False)

    add_section('Membership Status', cs.status_before, cs.status_after)
    add_section('RSI Handle', cs.handle_before, cs.handle_after)
    add_section('Community Moniker', cs.moniker_before, cs.moniker_after)
    add_section('Discord Nickname', cs.username_before, cs.username_after)

    if cs.roles_added:
        embed.add_field(name='Roles Added', value='\n'.join(f"• {r}" for r in cs.roles_added), inline=False)
    if cs.roles_removed:
        embed.add_field(name='Roles Removed', value='\n'.join(f"• {r}" for r in cs.roles_removed), inline=False)

    if cs.notes:
        embed.add_field(name='Notes', value=cs.notes, inline=False)

    # Footer
    handle = cs.handle_after or cs.handle_before or 'No Handle'
    timestamp = datetime.utcnow().replace(tzinfo=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    footer_text = f"{cs.user_id} • {handle} • {timestamp}"
    if handle and handle != 'No Handle':
        try:
            embed.url = f"https://robertsspaceindustries.com/citizens/{handle}"
        except Exception:  # pragma: no cover
            pass
    embed.set_footer(text=footer_text)
    return embed


def _summarize_roles(added: list[str], removed: list[str]) -> Optional[str]:  # legacy stub
    return None


def _truncate(value: Optional[str], length: int = 32) -> Optional[str]:
    if value is None:
        return None
    v = value.strip()
    if len(v) <= length:
        return v
    return v[: length - 1] + '…'


_MD_INLINE = set(['`','*','_','~','|','>'])


def _escape_inline(value: Optional[str]) -> str:
    if value is None:
        return ''
    out = []
    for ch in value:
        if ch in _MD_INLINE:
            out.append('\\' + ch)
        else:
            out.append(ch)
    return ''.join(out)


def _action_tag(cs: ChangeSet) -> str:
    return {
        EventType.VERIFICATION: 'User Verify',
        EventType.RECHECK: 'Admin Check' if cs.initiator_kind == 'Admin' and cs.event == EventType.RECHECK else 'Admin Check' if cs.event == EventType.ADMIN_CHECK else 'User Verify' if cs.event == EventType.RECHECK and cs.initiator_kind == 'User' else 'Auto Re-check' if cs.event == EventType.AUTO_CHECK else 'Admin Check' if cs.event == EventType.ADMIN_CHECK else cs.event.name,
        EventType.AUTO_CHECK: 'Auto Re-check',
        EventType.ADMIN_CHECK: 'Admin Check',
    }[cs.event]


def _outcome_and_emoji(cs: ChangeSet, changed_fields: int, had_changes: bool, first_verify: bool) -> tuple[str, str]:
    if not had_changes:
        return ('No changes', '🔎')
    if first_verify and cs.event == EventType.VERIFICATION:
        return ('Verified', '✅')
    return ('Updated', '🔁')


def _build_header(cs: ChangeSet, changed_fields: int, had_changes: bool) -> str:
    first_verify = cs.event == EventType.VERIFICATION and _changed_material(cs.status_before, cs.status_after)
    outcome, emoji = _outcome_and_emoji(cs, changed_fields, had_changes, first_verify)
    tag = _action_tag(cs)
    admin_part = ''
    if tag in ('Admin Check',) and cs.initiator_kind == 'Admin' and cs.initiator_name:
        admin_part = f" • Admin: {escape_md(_truncate(cs.initiator_name))}".replace('`','')  # header not code‑wrapped
    return f"[{tag}{admin_part}] <@{cs.user_id}> {emoji} {outcome}"


def _format_duration(ms: int) -> str:  # legacy stub (kept for compatibility)
    return ''


def _field_label_map() -> dict:
    return {
        'status': 'Status',
        'moniker': 'Moniker',
        'username': 'Nickname',
        'handle': 'Handle',
    }


def _render_plaintext(cs: ChangeSet) -> str:
    # Determine which fields changed materially
    changes = []
    if _changed_material(cs.status_before, cs.status_after):
        changes.append(('Status', _escape_inline(_truncate(cs.status_before or 'Non-Member')), _escape_inline(_truncate(cs.status_after or 'Non-Member'))))
    if _changed_material(cs.moniker_before, cs.moniker_after):
        changes.append(('Moniker', _escape_inline(_truncate(cs.moniker_before or '(none)')), _escape_inline(_truncate(cs.moniker_after or '(none)'))))
    if _changed_material(cs.username_before, cs.username_after):
        changes.append(('Nickname', _escape_inline(_truncate(cs.username_before or '(none)')), _escape_inline(_truncate(cs.username_after or '(none)'))))
    if _changed_material(cs.handle_before, cs.handle_after):
        changes.append(('Handle', _escape_inline(_truncate(cs.handle_before or '(none)')), _escape_inline(_truncate(cs.handle_after or '(none)'))))
    # Roles intentionally omitted from rendered output

    had_changes = bool(changes)
    header = _build_header(cs, len(changes), had_changes)

    duration_line = None
    if not had_changes:
        # Only for admin or user initiated checks we still post (handled by caller) with no change line
        return header

    # Single-line compact fallback (only exactly one changed field & not status promotion demotion complexity)
    if len(changes) == 1:
        label, before, after = changes[0]
        field_text = f"Roles: {after}" if label == 'Roles' else f"{label}: {before} → {after}"
        if cs.event == EventType.AUTO_CHECK:
            return f"[{_action_tag(cs)}] <@{cs.user_id}> 🔁 {field_text}"
        return f"{header}\n{field_text}"

    lines = [header]
    for label, before, after in changes:
        if label == 'Roles':
            lines.append(f"Roles: {after}")
        else:
            lines.append(f"{label}: {before} → {after}")
    if duration_line:
        lines.append(duration_line)
    return '\n'.join(lines)


async def post_if_changed(bot, cs: ChangeSet):
    # Normalize roles to managed set only; discard others for change signature & rendering
    managed_names = set(_managed_role_names(bot))
    if cs.roles_added:
        cs.roles_added = [r for r in cs.roles_added if r in managed_names]
    if cs.roles_removed:
        cs.roles_removed = [r for r in cs.roles_removed if r in managed_names]

    # Filter out case-only changes by rewriting after values to before when only case differs
    for attr_pair in [('moniker_before', 'moniker_after'), ('username_before', 'username_after'), ('handle_before', 'handle_after')]:
        b = getattr(cs, attr_pair[0])
        a = getattr(cs, attr_pair[1])
        if b and a and b.lower() == a.lower() and b != a:
            setattr(cs, attr_pair[1], b)  # revert to suppress

    unchanged = is_effectively_unchanged(cs, bot=bot)

    # Decide posting logic per new spec
    if cs.event == EventType.AUTO_CHECK and unchanged:
        return  # suppress
    if unchanged and cs.event in (EventType.RECHECK, EventType.ADMIN_CHECK):
        # We still post a "No changes" line
        pass

    if cs.event == EventType.VERIFICATION:
        # Always post
        pass
    if cs.event == EventType.RECHECK and cs.initiator_kind == 'User':
        # user recheck (button) -> treat as User Verify tag? spec says header tags: User Verify, Admin Check, Auto Re-check
        # We'll map to Admin Check only when initiator is Admin. Keep default mapping path (User Verify) in _action_tag for first verify only.
        pass

    # Dedupe short window
    sig = _normalize_signature(cs)
    key = (cs.user_id, sig)
    now = time.time()
    # Purge expired keys opportunistically
    if len(_DEDUP_CACHE) > 1000:  # safety bound
        expired = [k for k,v in _DEDUP_CACHE.items() if now - v > _DEDUP_TTL_SECONDS]
        for k in expired:
            _DEDUP_CACHE.pop(k, None)
    last = _DEDUP_CACHE.get(key)
    if last and now - last < _DEDUP_TTL_SECONDS:
        logger.debug('Leadership log deduped identical ChangeSet within window.')
        return
    _DEDUP_CACHE[key] = now

    # Channel resolution
    channel_id = None
    try:
        channel_id = (bot.config or {}).get('channels', {}).get('leadership_announcement_channel_id')
        if not channel_id and hasattr(bot, 'LEADERSHIP_LOG_CHANNEL_ID'):
            channel_id = getattr(bot, 'LEADERSHIP_LOG_CHANNEL_ID')
    except Exception:
        channel_id = getattr(bot, 'LEADERSHIP_LOG_CHANNEL_ID', None)
    if not channel_id:
        logger.debug('Leadership log channel not configured; skipping post.')
        return
    channel = bot.get_channel(int(channel_id)) if channel_id else None
    if not channel:
        logger.debug('Leadership log channel object not found; skipping.')
        return
    try:
        content = _render_plaintext(cs)
        await channel_send_message(channel, content, embed=None)  # plain text only now
    except Exception as e:
        logger.warning(f"Failed posting leadership log: {e}")


__all__ = [
    'EventType',
    'ChangeSet',
    'escape_md',
    'is_effectively_unchanged',
    'color_for',
    'build_message', 'build_embed',  # build_embed retained for backwards compatibility (may be removed later)
    'post_if_changed',
]
