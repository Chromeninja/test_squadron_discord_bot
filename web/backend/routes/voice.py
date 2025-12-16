"""
Voice channel search endpoints.
"""

import json
from typing import TYPE_CHECKING

from core.dependencies import (
    InternalAPIClient,
    get_db,
    get_internal_api_client,
    get_voice_service,
    require_moderator,
    require_staff,
)
from core.guild_settings import get_organization_settings
from core.pagination import (
    DEFAULT_PAGE_SIZE_VOICE,
    MAX_PAGE_SIZE_VOICE,
    clamp_page_size,
    is_all_guilds_mode,
)
from core.schemas import (
    ActiveVoiceChannel,
    ActiveVoiceChannelsResponse,
    GuildUserSettingsGroup,
    GuildVoiceGroup,
    JTCChannelSettings,
    PermissionEntry,
    PrioritySpeakerEntry,
    PTTSettingEntry,
    SoundboardEntry,
    UserJTCSettings,
    UserProfile,
    VoiceChannelRecord,
    VoiceSearchResponse,
    VoiceSettingsResetResponse,
    VoiceUserSettingsSearchResponse,
)
from core.validation import ensure_active_guild, parse_snowflake_id
from fastapi import APIRouter, Depends, HTTPException, Query

from helpers.audit import log_admin_action
from helpers.voice_settings import _get_last_used_jtc_channel
from services.db.database import derive_membership_status
from services.voice_service import VoiceService
from utils.logging import get_logger

if TYPE_CHECKING:
    from utils.types import VoiceSettingsSnapshot

logger = get_logger(__name__)

router = APIRouter()


async def _resolve_snapshot_targets_internal(
    snapshot: "VoiceSettingsSnapshot",
    guild_id: int,
    roles_map: dict[str, str],
    member_name_loader,
):
    """Resolve target names using cached roles and an async member name loader."""

    guild_id_str = str(guild_id)

    async def _resolve(entry) -> None:
        target_id = entry.target_id
        entry.is_everyone = target_id in ("0", guild_id_str)
        if entry.is_everyone:
            entry.target_name = "@everyone"
            entry.unknown_role = False
            return

        if entry.target_type == "role":
            name = roles_map.get(target_id)
            entry.target_name = f"@{name}" if name else None
            entry.unknown_role = name is None
            return

        try:
            entry.target_name = await member_name_loader(int(target_id))
        except (TypeError, ValueError):
            entry.target_name = None

    for entry in (
        list(snapshot.permissions)
        + list(snapshot.ptt_settings)
        + list(snapshot.priority_speaker_settings)
        + list(snapshot.soundboard_settings)
    ):
        await _resolve(entry)


def snapshot_to_jtc_settings(
    snapshot: "VoiceSettingsSnapshot", jtc_channel_name: str | None = None
) -> JTCChannelSettings:
    """
    Convert a VoiceSettingsSnapshot to JTCChannelSettings API response model.

    This ensures consistency between Discord commands and API responses.

    Args:
        snapshot: VoiceSettingsSnapshot with resolved target names

    Returns:
        JTCChannelSettings API model
    """

    # Convert permissions
    permissions = [
        PermissionEntry(
            target_id=perm.target_id,
            target_type=perm.target_type,
            permission=perm.permission,
            target_name=perm.target_name,
            is_everyone=perm.is_everyone,
            unknown_role=perm.unknown_role,
        )
        for perm in snapshot.permissions
    ]

    # Convert PTT settings
    ptt_settings = [
        PTTSettingEntry(
            target_id=ptt.target_id,
            target_type=ptt.target_type,
            ptt_enabled=ptt.ptt_enabled,
            target_name=ptt.target_name,
            is_everyone=ptt.is_everyone,
            unknown_role=ptt.unknown_role,
        )
        for ptt in snapshot.ptt_settings
    ]

    # Convert priority speaker settings
    priority_settings = [
        PrioritySpeakerEntry(
            target_id=priority.target_id,
            target_type=priority.target_type,
            priority_enabled=priority.priority_enabled,
            target_name=priority.target_name,
            is_everyone=priority.is_everyone,
            unknown_role=priority.unknown_role,
        )
        for priority in snapshot.priority_speaker_settings
    ]

    # Convert soundboard settings
    soundboard_settings = [
        SoundboardEntry(
            target_id=soundboard.target_id,
            target_type=soundboard.target_type,
            soundboard_enabled=soundboard.soundboard_enabled,
            target_name=soundboard.target_name,
            is_everyone=soundboard.is_everyone,
            unknown_role=soundboard.unknown_role,
        )
        for soundboard in snapshot.soundboard_settings
    ]

    return JTCChannelSettings(
        jtc_channel_id=str(snapshot.jtc_channel_id),
        jtc_channel_name=jtc_channel_name,
        channel_name=snapshot.channel_name,
        user_limit=snapshot.user_limit,
        lock=snapshot.is_locked,
        permissions=permissions,
        ptt_settings=ptt_settings,
        priority_settings=priority_settings,
        soundboard_settings=soundboard_settings,
    )


@router.get("/integrity")
async def voice_integrity_audit(
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_moderator()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Detect likely corrupted/unknown role IDs in voice settings tables for the active guild.

    Requires: Moderator role or higher

    Returns:
        { count: int, details: list[str] }
    """
    if not current_user.active_guild_id:
        return {"count": 0, "details": []}

    guild_id = int(current_user.active_guild_id)

    try:
        # Fetch current guild role IDs as strings
        roles = await internal_api.get_guild_roles(guild_id)
        valid_role_ids = {str(r.get("id")) for r in roles if r.get("id") is not None}

        details: list[str] = []

        # Tables that have role targets
        role_tables = [
            ("channel_permissions", "target_id", "target_type"),
            ("channel_ptt_settings", "target_id", "target_type"),
            ("channel_priority_speaker_settings", "target_id", "target_type"),
            ("channel_soundboard_settings", "target_id", "target_type"),
        ]

        for table, col_id, col_type in role_tables:
            cursor = await db.execute(
                f"SELECT rowid, {col_id}, {col_type} FROM {table} WHERE guild_id = ? AND {col_type} = 'role'",
                (guild_id,),
            )
            rows = await cursor.fetchall()
            for rowid, target_id, _ in rows:
                sid = str(target_id)
                if sid not in valid_role_ids:
                    details.append(f"{table} rowid {rowid}: ID {sid}")

        return {"count": len(details), "details": details}

    except Exception as e:
        logger.exception("Integrity audit failed", exc_info=e)
        # Fail closed but non-fatal for UI
        return {"count": 0, "details": []}


@router.get("/active", response_model=ActiveVoiceChannelsResponse)
async def list_active_voice_channels(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page (max 100)"),
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_staff()),
    voice_service: VoiceService = Depends(get_voice_service),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """List all active voice channels with owner information and current members.

    Returns active voice channels with real-time member data from Discord API.
    Filters by the user's currently active guild.
    Bot owners in "All Guilds" mode can view channels across all guilds (grouped by guild).

    Requires: Staff role or higher

    Returns:
        ActiveVoiceChannelsResponse with active channel list
    """
    # Apply pagination caps
    page_size = clamp_page_size(page_size, DEFAULT_PAGE_SIZE_VOICE, MAX_PAGE_SIZE_VOICE)

    is_cross_guild = is_all_guilds_mode(current_user.active_guild_id)

    # Ensure user has an active guild selected
    if not current_user.active_guild_id:
        return ActiveVoiceChannelsResponse(items=[], total=0, is_cross_guild=False)

    if is_cross_guild:
        # Cross-guild mode: fetch all active voice channels across all guilds
        cursor = await db.execute(
            """
            SELECT
                vc.voice_channel_id,
                vc.guild_id,
                vc.jtc_channel_id,
                vc.owner_id,
                vc.created_at,
                vc.last_activity,
                v.rsi_handle,
                v.main_orgs,
                v.affiliate_orgs
            FROM voice_channels vc
            LEFT JOIN verification v ON vc.owner_id = v.user_id
            WHERE vc.is_active = 1
            ORDER BY vc.guild_id, vc.last_activity DESC
            """,
        )
        rows = await cursor.fetchall()

        if not rows:
            return ActiveVoiceChannelsResponse(
                items=[], total=0, is_cross_guild=True, guild_groups=[]
            )

        # Get guild metadata for names
        try:
            guilds_list = await internal_api.get_guilds()
            guild_map = {
                str(g.get("guild_id")): g.get("guild_name", f"Guild {g.get('guild_id')}")
                for g in guilds_list
            }
        except Exception:
            guild_map = {}

        # Apply pagination to total rows
        offset = (page - 1) * page_size
        total = len(rows)
        rows_paged = rows[offset:offset + page_size]

        # Build items with minimal enrichment (no Discord API calls in cross-guild mode)
        items = []
        guild_items: dict[str, list[ActiveVoiceChannel]] = {}

        for row in rows_paged:
            guild_id = row[1]
            guild_id_str = str(guild_id)
            guild_name = guild_map.get(guild_id_str, f"Guild {guild_id}")

            owner_main_orgs = json.loads(row[7]) if row[7] else None
            owner_aff_orgs = json.loads(row[8]) if row[8] else None

            if owner_main_orgs is None and owner_aff_orgs is None:
                owner_status = "unknown"
            else:
                owner_status = derive_membership_status(
                    owner_main_orgs or [], owner_aff_orgs or []
                )

            channel = ActiveVoiceChannel(
                voice_channel_id=row[0],
                guild_id=row[1],
                jtc_channel_id=row[2],
                owner_id=row[3],
                created_at=row[4],
                last_activity=row[5],
                owner_rsi_handle=row[6],
                owner_membership_status=owner_status,
                channel_name=f"Channel {row[0]}",  # No Discord enrichment in cross-guild
                members=[],  # No member enrichment in cross-guild
                guild_name=guild_name,
            )

            items.append(channel)

            if guild_id_str not in guild_items:
                guild_items[guild_id_str] = []
            guild_items[guild_id_str].append(channel)

        # Build guild groups
        guild_groups = [
            GuildVoiceGroup(
                guild_id=gid,
                guild_name=guild_map.get(gid, f"Guild {gid}"),
                items=channels,
            )
            for gid, channels in guild_items.items()
        ]

        return ActiveVoiceChannelsResponse(
            items=items,
            total=total,
            is_cross_guild=True,
            guild_groups=guild_groups,
        )

    # Single-guild mode (original behavior)
    # Query active voice channels with owner verification info
    # FILTER BY GUILD ID to only show channels for the active guild
    cursor = await db.execute(
        """
        SELECT
            vc.voice_channel_id,
            vc.guild_id,
            vc.jtc_channel_id,
            vc.owner_id,
            vc.created_at,
            vc.last_activity,
            v.rsi_handle,
            v.main_orgs,
            v.affiliate_orgs
        FROM voice_channels vc
        LEFT JOIN verification v ON vc.owner_id = v.user_id
        WHERE vc.is_active = 1 AND vc.guild_id = ?
        ORDER BY vc.last_activity DESC
        """,
        (current_user.active_guild_id,),
    )
    rows = await cursor.fetchall()

    if not rows:
        return ActiveVoiceChannelsResponse(items=[], total=0, is_cross_guild=False)

    # Fetch channel details and members via internal bot API (no direct Discord calls)
    items = []

    for row in rows:
        voice_channel_id = row[0]
        guild_id = row[1]
        owner_id = row[3]
        # Derive owner membership status from org lists
        owner_main_orgs = json.loads(row[7]) if row[7] else None
        owner_aff_orgs = json.loads(row[8]) if row[8] else None
        # Fetch org SID for guild if available
        org_settings = await get_organization_settings(db, guild_id)
        organization_sid = (
            org_settings.get("organization_sid") if org_settings else None
        )

        # Derive owner status using standard logic (filters REDACTED)
        if owner_main_orgs is None and owner_aff_orgs is None:
            owner_status = "unknown"
        else:
            owner_status = derive_membership_status(
                owner_main_orgs or [],
                owner_aff_orgs or [],
                organization_sid or "TEST"
            )

        try:
            # Get channel info from internal API (cached via bot's gateway)
            channel_name = f"Channel {voice_channel_id}"
            try:
                all_channels = await internal_api.get_guild_channels(guild_id)
                channel_data = next(
                    (c for c in all_channels if str(c.get("id")) == str(voice_channel_id)),
                    None,
                )
                if channel_data:
                    channel_name = channel_data.get("name", channel_name)
            except Exception:
                logger.debug(
                    "Could not fetch channel info from internal API for %s",
                    voice_channel_id,
                )

            # Prefer saved channel settings name if available via snapshot logic
            snapshot = await voice_service.get_voice_settings_snapshot(
                guild_id=guild_id,
                jtc_channel_id=row[2],
                owner_id=owner_id,
                voice_channel_id=voice_channel_id,
            )
            if snapshot and snapshot.channel_name:
                channel_name = snapshot.channel_name

            # Get member IDs from bot's internal API (Gateway cache - no Discord API calls!)
            member_ids = []
            try:
                member_ids = await internal_api.get_voice_channel_members(voice_channel_id)
            except Exception:
                logger.debug(
                    "Could not fetch voice members from internal API for channel %s",
                    voice_channel_id,
                )
                # Fall back to just showing owner
                member_ids = [owner_id]

            # Ensure owner is always in the list
            if owner_id not in member_ids:
                member_ids.append(owner_id)

            # Get verification info for members (status derived from org lists)
            members_in_channel = []
            if member_ids:
                placeholders = ",".join("?" * len(member_ids))
                members_cursor = await db.execute(
                    f"""
                    SELECT user_id, rsi_handle, main_orgs, affiliate_orgs
                    FROM verification
                    WHERE user_id IN ({placeholders})
                    """,
                    tuple(member_ids),
                )
                fetched = await members_cursor.fetchall()
                verification_data = {
                    r[0]: {
                        "rsi_handle": r[1],
                        "main_orgs": json.loads(r[2]) if r[2] else None,
                        "affiliate_orgs": json.loads(r[3]) if r[3] else None,
                    }
                    for r in fetched
                }

                # Build members list
                for user_id in member_ids:
                    verification = verification_data.get(user_id, {})

                    # Get Discord user info via internal API (cached via bot's gateway)
                    username = None
                    try:
                        member_data = await internal_api.get_guild_member(guild_id, user_id)
                        username = member_data.get("username")
                    except Exception:
                        pass

                    members_in_channel.append(
                        {
                            "user_id": user_id,
                            "username": username,
                            "display_name": verification.get("rsi_handle")
                            or username
                            or f"User {user_id}",
                            "rsi_handle": verification.get("rsi_handle"),
                            "membership_status": (
                                "unknown" if verification.get("main_orgs") is None and verification.get("affiliate_orgs") is None
                                else derive_membership_status(
                                    verification.get("main_orgs") or [],
                                    verification.get("affiliate_orgs") or [],
                                    organization_sid or "TEST"
                                )
                            ),
                            "is_owner": user_id == owner_id,
                        }
                    )

            items.append(
                ActiveVoiceChannel(
                    voice_channel_id=row[0],
                    guild_id=row[1],
                    jtc_channel_id=row[2],
                    owner_id=row[3],
                    created_at=row[4],
                    last_activity=row[5],
                    owner_rsi_handle=row[6],
                    owner_membership_status=owner_status,
                    channel_name=channel_name,
                    members=members_in_channel,
                )
            )

        except Exception:
            logger.exception(
                "Error fetching data for channel %s", voice_channel_id
            )
            # Add channel with minimal data
            items.append(
                ActiveVoiceChannel(
                    voice_channel_id=row[0],
                    guild_id=row[1],
                    jtc_channel_id=row[2],
                    owner_id=row[3],
                    created_at=row[4],
                    last_activity=row[5],
                    owner_rsi_handle=row[6],
                    owner_membership_status=owner_status,
                    channel_name=f"Channel {row[0]}",
                    members=[],
                )
            )

    return ActiveVoiceChannelsResponse(items=items, total=len(items), is_cross_guild=False)


@router.get("/search", response_model=VoiceSearchResponse)
async def search_voice_channels(
    user_id: int = Query(..., description="Discord user ID to search for"),
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_staff()),
    voice_service: VoiceService = Depends(get_voice_service),
):
    """
    Search voice channels by owner user ID.

    Returns all voice channel records for the specified user,
    ordered by most recent activity.

    Requires: Staff role or higher

    Args:
        user_id: Discord user ID

    Returns:
        VoiceSearchResponse with matching voice channel records
    """
    # Query voice_channels for the user
    cursor = await db.execute(
        """
        SELECT
            id, guild_id, jtc_channel_id, owner_id,
            voice_channel_id, created_at, last_activity, is_active
        FROM voice_channels
        WHERE owner_id = ?
        ORDER BY last_activity DESC
        """,
        (user_id,),
    )
    rows = await cursor.fetchall()

    # Convert to VoiceChannelRecord objects
    items = []
    for row in rows:
        snapshot = await voice_service.get_voice_settings_snapshot(
            guild_id=row[1],
            jtc_channel_id=row[2],
            owner_id=row[3],
            voice_channel_id=row[4],
        )
        created_at_val = snapshot.created_at if snapshot else row[5]
        last_activity_val = snapshot.last_activity if snapshot else row[6]
        items.append(
            VoiceChannelRecord(
                id=row[0],
                guild_id=row[1],
                jtc_channel_id=row[2],
                owner_id=row[3],
                voice_channel_id=row[4],
                created_at=int(created_at_val or 0),
                last_activity=int(last_activity_val or 0),
                is_active=bool(snapshot.is_active) if snapshot else bool(row[7]),
            )
        )

    return VoiceSearchResponse(
        success=True,
        items=items,
        total=len(items),
    )


@router.get("/user-settings", response_model=VoiceUserSettingsSearchResponse)
async def search_user_voice_settings(
    query: str = Query(..., description="Search by Discord user ID or RSI handle"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_staff()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
    voice_service: VoiceService = Depends(get_voice_service),
):
    """
    Search for users and their saved JTC voice settings using unified snapshot system.

    Search by:
    - Discord user ID (exact match if numeric)
    - RSI handle (case-insensitive partial match)

    Returns all saved JTC settings for each matched user in the currently active guild.
    In "All Guilds" mode, returns settings across all guilds grouped by guild.

    Requires: Staff role or higher

    Args:
        query: Search term (Discord ID or RSI handle)
        page: Page number (1-indexed)
        page_size: Results per page (max 100)

    Returns:
        VoiceUserSettingsSearchResponse with paginated user settings
    """
    # Apply pagination caps
    page_size = clamp_page_size(page_size, DEFAULT_PAGE_SIZE_VOICE, MAX_PAGE_SIZE_VOICE)

    is_cross_guild = is_all_guilds_mode(current_user.active_guild_id)

    # Ensure user has an active guild selected
    if not current_user.active_guild_id:
        return VoiceUserSettingsSearchResponse(
            success=True,
            items=[],
            total=0,
            page=page,
            page_size=page_size,
            message="No active guild selected",
            is_cross_guild=False,
        )

    if is_cross_guild:
        # Cross-guild mode: search across all guilds
        offset = (page - 1) * page_size

        # Get guild metadata for names
        try:
            guilds_list = await internal_api.get_guilds()
            guild_map = {
                str(g.get("guild_id")): g.get("guild_name", f"Guild {g.get('guild_id')}")
                for g in guilds_list
            }
            guild_ids = [int(gid) for g in guilds_list if (gid := g.get("guild_id")) is not None]
        except Exception:
            guild_map = {}
            guild_ids = []

        if not guild_ids:
            return VoiceUserSettingsSearchResponse(
                success=True,
                items=[],
                total=0,
                page=page,
                page_size=page_size,
                message="No guilds available",
                is_cross_guild=True,
                guild_groups=[],
            )

        # Search for users by query
        try:
            user_id_int = int(query)
            # Exact user ID search
            verification_cursor = await db.execute(
                "SELECT user_id, rsi_handle, community_moniker FROM verification WHERE user_id = ?",
                (user_id_int,),
            )
            verification_rows = await verification_cursor.fetchall()
        except ValueError:
            # RSI handle search
            search_pattern = f"%{query}%"
            verification_cursor = await db.execute(
                """
                SELECT user_id, rsi_handle, community_moniker
                FROM verification
                WHERE rsi_handle LIKE ?
                ORDER BY rsi_handle
                LIMIT ? OFFSET ?
                """,
                (search_pattern, page_size, offset),
            )
            verification_rows = await verification_cursor.fetchall()

        # Build items with settings from all guilds
        items = []
        guild_items: dict[str, list[UserJTCSettings]] = {}

        for ver_row in verification_rows:
            user_id = ver_row[0]
            rsi_handle = ver_row[1]
            community_moniker = ver_row[2]

            # Check each guild for voice settings
            for gid in guild_ids:
                gid_str = str(gid)
                snapshots = await voice_service.get_user_settings_snapshots(gid, user_id)

                if not snapshots:
                    continue

                primary_jtc_id = await _get_last_used_jtc_channel(gid, user_id)

                # Minimal resolution (no Discord API calls in cross-guild)
                resolved_jtcs = [
                    snapshot_to_jtc_settings(s, jtc_channel_name=f"JTC {s.jtc_channel_id}")
                    for s in snapshots
                ]

                user_settings = UserJTCSettings(
                    user_id=str(user_id),
                    rsi_handle=rsi_handle,
                    community_moniker=community_moniker,
                    primary_jtc_id=str(primary_jtc_id) if primary_jtc_id else None,
                    jtcs=resolved_jtcs,
                    guild_id=gid_str,
                    guild_name=guild_map.get(gid_str, f"Guild {gid}"),
                )

                items.append(user_settings)

                if gid_str not in guild_items:
                    guild_items[gid_str] = []
                guild_items[gid_str].append(user_settings)

        # Build guild groups
        guild_groups = [
            GuildUserSettingsGroup(
                guild_id=gid,
                guild_name=guild_map.get(gid, f"Guild {gid}"),
                items=settings,
            )
            for gid, settings in guild_items.items()
        ]

        return VoiceUserSettingsSearchResponse(
            success=True,
            items=items,
            total=len(items),
            page=page,
            page_size=page_size,
            is_cross_guild=True,
            guild_groups=guild_groups,
        )

    guild_id = int(current_user.active_guild_id)
    offset = (page - 1) * page_size

    # First, get the set of user IDs who are actually members of this guild
    # This prevents privacy issues where users can see settings for users not in their guild
    # Use None as sentinel for "no filtering needed", empty set means "no members found"
    guild_member_ids: set[int] | None = None
    try:
        guild_member_ids = set()
        page_num = 1
        fetch_size = 1000  # Max supported by API
        while True:
            members_data = await internal_api.get_guild_members(
                guild_id, page=page_num, page_size=fetch_size
            )
            members_list = members_data.get("members", [])
            for m in members_list:
                if m.get("user_id"):
                    guild_member_ids.add(int(m["user_id"]))
            if len(members_list) < fetch_size:
                break
            page_num += 1
    except Exception:
        logger.warning("Failed to fetch guild members for privacy filtering, returning empty results (fail closed)")
        # Fail closed: return empty results rather than exposing settings for non-members
        return VoiceUserSettingsSearchResponse(
            success=True,
            items=[],
            total=0,
            page=page,
            page_size=page_size,
            message="Unable to verify guild membership",
            is_cross_guild=False,
        )

    # Fetch guild roles for name resolution (per snapshot helper)
    try:
        guild_roles = await internal_api.get_guild_roles(guild_id)
        roles_map = {
            str(role["id"]): role_name
            for role in guild_roles
            if (role_name := role.get("name")) is not None
        }
    except Exception:
        logger.exception("Error fetching guild roles")
        roles_map = {}

    # Cache for member data
    members_cache: dict[int, str | None] = {}

    async def get_member_name(user_id: int) -> str | None:
        if user_id in members_cache:
            return members_cache[user_id]
        try:
            member = await internal_api.get_guild_member(guild_id, user_id)
            name = (
                member.get("nick")
                or member.get("global_name")
                or member.get("username")
            )
            members_cache[user_id] = name
            return name
        except Exception:
            members_cache[user_id] = None
            return None

    # Resolve users from verification table
    # Try exact user_id match first if query is numeric
    try:
        user_id_int = int(query)

        candidate_user_ids: set[int] = set()
        verification_map: dict[int, tuple[str | None, str | None]] = {}

        # Exact Discord ID match from verification (existing behavior)
        verification_cursor = await db.execute(
            """
            SELECT user_id, rsi_handle, community_moniker
            FROM verification
            WHERE user_id = ?
            """,
            (user_id_int,),
        )
        verification_row = await verification_cursor.fetchone()
        if verification_row:
            candidate_user_ids.add(user_id_int)
            verification_map[user_id_int] = (
                verification_row[1],
                verification_row[2],
            )

        # Also include users that have voice settings but are not verified (single-row lookup)
        voice_row_cursor = await db.execute(
            """
            SELECT 1 FROM channel_settings
            WHERE guild_id = ? AND user_id = ?
            LIMIT 1
            """,
            (guild_id, user_id_int),
        )
        voice_row = await voice_row_cursor.fetchone()
        if voice_row:
            candidate_user_ids.add(user_id_int)

        # Filter to only include users who are actually members of this guild
        # guild_member_ids is always a set here (we return early on fetch failure)
        candidate_user_ids = candidate_user_ids & guild_member_ids

        total = len(candidate_user_ids)

        candidate_user_ids_sorted = sorted(candidate_user_ids)
        paged_user_ids = candidate_user_ids_sorted[offset : offset + page_size]

        # Build rows list to align with existing processing loop
        rows = [
            (
                uid,
                verification_map.get(uid, (None, None))[0],
                verification_map.get(uid, (None, None))[1],
            )
            for uid in paged_user_ids
        ]
    except ValueError:
        # Not a valid integer, search by RSI handle with LIKE (verification-only)
        search_pattern = f"%{query}%"

        # Fetch all matching rows first, then filter by guild membership
        cursor = await db.execute(
            """
            SELECT user_id, rsi_handle, community_moniker
            FROM verification
            WHERE rsi_handle LIKE ?
            ORDER BY rsi_handle
            """,
            (search_pattern,),
        )
        all_rows = await cursor.fetchall()

        # Filter to only include users who are actually members of this guild
        # guild_member_ids is always a set here (we return early on fetch failure)
        rows_filtered = [r for r in all_rows if int(r[0]) in guild_member_ids]

        total = len(rows_filtered)
        rows = rows_filtered[offset : offset + page_size]

    items = []

    # Fetch all JTC channels for the guild to get their names
    jtc_channels_map: dict[str, str] = {}
    try:
        all_channels = await internal_api.get_guild_channels(guild_id)
        jtc_channels_map = {
            str(ch["id"]): ch.get("name", f"Channel {ch['id']}")
            for ch in all_channels
            if ch.get("type") in (2, 13)
        }
    except Exception as e:
        logger.warning(f"Failed to fetch guild channels for JTC name resolution: {e}")

    for row in rows:
        user_id = row[0]
        rsi_handle = row[1]
        community_moniker = row[2]

        snapshots = await voice_service.get_user_settings_snapshots(guild_id, user_id)
        primary_jtc_id = await _get_last_used_jtc_channel(guild_id, user_id)

        resolved_jtcs: list[JTCChannelSettings] = []
        for snapshot in snapshots:
            await _resolve_snapshot_targets_internal(
                snapshot, guild_id, roles_map, get_member_name
            )
            jtc_name = jtc_channels_map.get(
                str(snapshot.jtc_channel_id), f"JTC {snapshot.jtc_channel_id}"
            )
            resolved_jtcs.append(
                snapshot_to_jtc_settings(snapshot, jtc_channel_name=jtc_name)
            )

        # Add user settings record (even if jtcs is empty)
        items.append(
            UserJTCSettings(
                user_id=str(user_id),
                rsi_handle=rsi_handle,
                community_moniker=community_moniker,
                primary_jtc_id=str(primary_jtc_id) if primary_jtc_id else None,
                jtcs=resolved_jtcs,
            )
        )

    return VoiceUserSettingsSearchResponse(
        success=True,
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        is_cross_guild=False,
    )


@router.delete("/user-settings/{user_id}", response_model=VoiceSettingsResetResponse)
async def reset_user_voice_settings(
    user_id: str,
    jtc_channel_id: int | None = Query(
        None, description="Optional JTC channel ID to reset only specific JTC settings"
    ),
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_moderator()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Reset voice settings for a user.

    Follows the bot's /voice admin reset command pattern:
    1. Deletes user's owned voice channel if it exists
    2. Purges voice-related database records
    3. Clears managed channel cache

    Scope:
    - If jtc_channel_id is provided: Reset only settings for that specific JTC
    - If jtc_channel_id is None: Reset ALL voice settings for user in guild (guild-wide)

    Requires: Admin role (following bot's @require_admin pattern)

    Args:
        user_id: Discord user ID to reset
        jtc_channel_id: Optional JTC channel ID for scoped reset

    Returns:
        VoiceSettingsResetResponse with deletion summary
    """
    # Use validation utilities for consistent guild and ID validation
    guild_id = ensure_active_guild(current_user)
    user_id_int = parse_snowflake_id(user_id, "User ID")

    # Require admin role for destructive operations (following bot pattern)
    def _is_admin_for_guild(user: UserProfile, gid: int) -> bool:
        perm = user.authorized_guilds.get(str(guild_id)) if user else None
        return bool(perm and perm.role_level in {"bot_owner", "bot_admin", "discord_manager"})

    if not _is_admin_for_guild(current_user, guild_id):
        raise HTTPException(
            status_code=403,
            detail="Admin role required for voice settings reset operations",
        )

    action_type = "RESET_USER_VOICE_SETTINGS"

    try:
        # Log the action
        action_type = (
            "RESET_USER_JTC_SETTINGS" if jtc_channel_id else "RESET_USER_VOICE_SETTINGS"
        )
        action_details = f"Admin {current_user.username} ({current_user.user_id}) resetting voice data for user {user_id} in guild {guild_id}"
        if jtc_channel_id:
            action_details += f" (JTC: {jtc_channel_id})"

        logger.info(action_details)

        # Get user's active voice channel info before deletion
        channel_deleted = False
        channel_id = None

        # Check if user has an active voice channel (best-effort info)
        cursor = await db.execute(
            "SELECT voice_channel_id FROM voice_channels WHERE guild_id = ? AND owner_id = ? AND is_active = 1",
            (guild_id, user_id_int),
        )
        row = await cursor.fetchone()
        if row:
            channel_id = row[0]
            # Deleting the live Discord channel requires an internal endpoint.
            # This API currently performs DB cleanup only
            # We keep the channel_id in response for transparency.
            channel_deleted = False

        # Step 2: Purge database records
        if jtc_channel_id:
            # JTC-scoped reset: Only delete settings for specific JTC
            from services.db.database import Database

            deleted_counts = {}
            jtc_tables = [
                "channel_settings",
                "channel_permissions",
                "channel_ptt_settings",
                "channel_priority_speaker_settings",
                "channel_soundboard_settings",
            ]

            await db.execute("BEGIN TRANSACTION")
            try:
                for table in jtc_tables:
                    cursor = await db.execute(
                        f"DELETE FROM {table} WHERE guild_id = ? AND user_id = ? AND jtc_channel_id = ?",
                        (guild_id, user_id_int, jtc_channel_id),
                    )
                    deleted_counts[table] = cursor.rowcount
                await db.commit()
                logger.info(
                    f"JTC-scoped reset complete - {deleted_counts} for user {user_id} JTC {jtc_channel_id}"
                )
            except Exception as e:
                await db.rollback()
                logger.exception(
                    f"Failed to purge JTC-scoped voice data: {e}", exc_info=e
                )
                raise
        else:
            # Guild-wide reset: Purge all voice data for user in guild
            from services.db.database import Database

            deleted_counts = await Database.purge_voice_data(guild_id, user_id_int)

        # Calculate totals
        total_rows = sum(deleted_counts.values())

        # Log detailed breakdown
        for table, count in deleted_counts.items():
            if count > 0:
                logger.info(
                    f"Voice reset - {table}: {count} records deleted for user {user_id}"
                )

        if channel_deleted:
            logger.info(f"Voice reset - channel {channel_id} successfully deleted")
        elif channel_id:
            logger.warning(f"Voice reset - channel {channel_id} deletion failed")

        # Log admin action to audit table
        scope_desc = f"JTC {jtc_channel_id}" if jtc_channel_id else "guild-wide"
        await log_admin_action(
            admin_user_id=int(current_user.user_id),
            guild_id=guild_id,
            action=action_type,
            target_user_id=user_id_int,
            details={
                "scope": scope_desc,
                "total_rows_deleted": total_rows,
                "channel_deleted": channel_deleted,
                "deleted_counts": deleted_counts,
            },
            status="success",
        )

        # Build response message
        message = f"Successfully reset voice data for user {user_id}"
        if jtc_channel_id:
            message += f" (JTC {jtc_channel_id})"
        message += f": {total_rows} total records deleted"

        return VoiceSettingsResetResponse(
            success=True,
            message=message,
            channel_deleted=channel_deleted,
            channel_id=channel_id,
            deleted_counts=deleted_counts,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error resetting user voice settings", exc_info=e)
        # Log failed action
        await log_admin_action(
            admin_user_id=int(current_user.user_id),
            guild_id=guild_id,
            action=action_type,
            target_user_id=user_id_int,
            details={
                "error": str(e),
            },
            status="error",
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to reset voice settings: {e!s}"
        )
