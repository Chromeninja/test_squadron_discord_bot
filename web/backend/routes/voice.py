"""
Voice channel search endpoints.
"""

import json
import os

import httpx
from core.dependencies import (
    InternalAPIClient,
    get_db,
    get_internal_api_client,
    require_admin_or_moderator,
)
from core.guild_settings import get_organization_settings
from core.schemas import (
    ActiveVoiceChannel,
    ActiveVoiceChannelsResponse,
    JTCChannelSettings,
    PermissionEntry,
    PrioritySpeakerEntry,
    PTTSettingEntry,
    SoundboardEntry,
    UserJTCSettings,
    UserProfile,
    VoiceChannelRecord,
    VoiceSearchResponse,
    VoiceUserSettingsSearchResponse,
)
from fastapi import APIRouter, Depends, Query

from helpers.voice_settings import (
    _get_all_user_jtc_settings,
    _get_last_used_jtc_channel,
)

router = APIRouter()

# Discord API configuration
DISCORD_BOT_TOKEN = os.getenv("DISCORD_TOKEN", "")
DISCORD_API_BASE = "https://discord.com/api/v10"

# Internal API configuration (bot-to-web communication)
# This points to the bot's internal API server (no Discord API calls)
INTERNAL_API_URL = os.getenv("INTERNAL_API_URL", "http://127.0.0.1:8082")
INTERNAL_API_KEY = os.getenv(
    "INTERNAL_API_KEY", "dev_internal_api_key_change_in_production"
)


@router.get("/active", response_model=ActiveVoiceChannelsResponse)
async def list_active_voice_channels(
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_admin_or_moderator),
):
    """
    List all active voice channels with owner information and current members.

    Returns active voice channels with real-time member data from Discord API.
    Filters by the user's currently active guild.

    Requires: Admin or moderator role

    Returns:
        ActiveVoiceChannelsResponse with active channel list
    """
    # Ensure user has an active guild selected
    if not current_user.active_guild_id:
        return ActiveVoiceChannelsResponse(items=[], total=0)

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
        return ActiveVoiceChannelsResponse(items=[], total=0)

    # Fetch channel details and members from Discord API and internal bot API
    async with httpx.AsyncClient() as client:
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

            def _derive(owner_main, owner_aff, sid):
                if owner_main is None and owner_aff is None:
                    return "unknown"
                mo = [s.upper() for s in (owner_main or [])]
                ao = [s.upper() for s in (owner_aff or [])]
                if sid:
                    s2 = sid.upper()
                    if s2 in mo:
                        return "main"
                    if s2 in ao:
                        return "affiliate"
                if mo:
                    return "main"
                if ao:
                    return "affiliate"
                return "non_member"

            owner_status = _derive(owner_main_orgs, owner_aff_orgs, organization_sid)

            try:
                # Get channel info from Discord API (for channel name)
                channel_response = await client.get(
                    f"{DISCORD_API_BASE}/channels/{voice_channel_id}",
                    headers={"Authorization": f"Bot {DISCORD_BOT_TOKEN}"},
                    timeout=5.0,
                )

                channel_name = f"Channel {voice_channel_id}"
                if channel_response.status_code == 200:
                    channel_data = channel_response.json()
                    channel_name = channel_data.get("name", channel_name)

                # Get member IDs from bot's internal API (Gateway cache - no Discord API calls!)
                member_ids = []
                try:
                    headers = {}
                    if INTERNAL_API_KEY:
                        headers["Authorization"] = f"Bearer {INTERNAL_API_KEY}"

                    internal_response = await client.get(
                        f"{INTERNAL_API_URL}/voice/members/{voice_channel_id}",
                        headers=headers,
                        timeout=3.0,
                    )

                    if internal_response.status_code == 200:
                        internal_data = internal_response.json()
                        member_ids = internal_data.get("member_ids", [])
                    else:
                        print(
                            f"Internal API returned {internal_response.status_code} for channel {voice_channel_id}"
                        )
                        # Fall back to just showing owner
                        member_ids = [owner_id]
                except Exception as e:
                    print(
                        f"Error querying internal API for channel {voice_channel_id}: {e}"
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

                        # Fetch Discord user info for username
                        username = None
                        try:
                            user_response = await client.get(
                                f"{DISCORD_API_BASE}/users/{user_id}",
                                headers={"Authorization": f"Bot {DISCORD_BOT_TOKEN}"},
                                timeout=3.0,
                            )
                            if user_response.status_code == 200:
                                user_data = user_response.json()
                                username = user_data.get("username")
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
                                "membership_status": _derive(
                                    verification.get("main_orgs"),
                                    verification.get("affiliate_orgs"),
                                    organization_sid,
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

            except Exception as e:
                print(
                    f"Error fetching Discord data for channel {voice_channel_id}: {e}"
                )
                import traceback

                traceback.print_exc()
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

    return ActiveVoiceChannelsResponse(items=items, total=len(items))


@router.get("/search", response_model=VoiceSearchResponse)
async def search_voice_channels(
    user_id: int = Query(..., description="Discord user ID to search for"),
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_admin_or_moderator),
):
    """
    Search voice channels by owner user ID.

    Returns all voice channel records for the specified user,
    ordered by most recent activity.

    Requires: Admin or moderator role

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
        items.append(
            VoiceChannelRecord(
                id=row[0],
                guild_id=row[1],
                jtc_channel_id=row[2],
                owner_id=row[3],
                voice_channel_id=row[4],
                created_at=row[5],
                last_activity=row[6],
                is_active=bool(row[7]),
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
    current_user: UserProfile = Depends(require_admin_or_moderator),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Search for users and their saved JTC voice settings.

    Search by:
    - Discord user ID (exact match if numeric)
    - RSI handle (case-insensitive partial match)

    Returns all saved JTC settings for each matched user in the currently active guild.

    Requires: Admin or moderator role

    Args:
        query: Search term (Discord ID or RSI handle)
        page: Page number (1-indexed)
        page_size: Results per page (max 100)

    Returns:
        VoiceUserSettingsSearchResponse with paginated user settings
    """
    # Ensure user has an active guild selected
    if not current_user.active_guild_id:
        return VoiceUserSettingsSearchResponse(
            success=True,
            items=[],
            total=0,
            page=page,
            page_size=page_size,
            message="No active guild selected",
        )

    guild_id = int(current_user.active_guild_id)
    offset = (page - 1) * page_size

    # Fetch guild roles and members for enrichment
    try:
        guild_roles = await internal_api.get_guild_roles(guild_id)
        # Use string keys for role IDs
        roles_map = {str(role["id"]): role["name"] for role in guild_roles}
    except Exception as e:
        import traceback

        print(f"Error fetching guild roles: {e}")
        print(traceback.format_exc())
        roles_map = {}

    # Cache for member data
    members_cache = {}

    async def get_member_name(user_id: int) -> str | None:
        """Get member nickname or username from cache or API."""
        if user_id in members_cache:
            return members_cache[user_id]
        try:
            member = await internal_api.get_guild_member(guild_id, user_id)
            # Prefer nick > global_name > username
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
        # Exact Discord ID match
        count_cursor = await db.execute(
            "SELECT COUNT(*) FROM verification WHERE user_id = ?",
            (user_id_int,),
        )
        count_row = await count_cursor.fetchone()
        total = count_row[0] if count_row else 0

        cursor = await db.execute(
            """
            SELECT user_id, rsi_handle, community_moniker
            FROM verification
            WHERE user_id = ?
            LIMIT ? OFFSET ?
            """,
            (user_id_int, page_size, offset),
        )
        rows = await cursor.fetchall()
    except ValueError:
        # Not a valid integer, search by RSI handle with LIKE
        search_pattern = f"%{query}%"

        count_cursor = await db.execute(
            "SELECT COUNT(*) FROM verification WHERE rsi_handle LIKE ?",
            (search_pattern,),
        )
        count_row = await count_cursor.fetchone()
        total = count_row[0] if count_row else 0

        cursor = await db.execute(
            """
            SELECT user_id, rsi_handle, community_moniker
            FROM verification
            WHERE rsi_handle LIKE ?
            ORDER BY rsi_handle
            LIMIT ? OFFSET ?
            """,
            (search_pattern, page_size, offset),
        )
        rows = await cursor.fetchall()

    # Build response items with JTC settings for each user
    items = []
    for row in rows:
        user_id = row[0]
        rsi_handle = row[1]
        community_moniker = row[2]

        # Fetch all JTC settings for this user in the current guild
        all_jtc_settings = await _get_all_user_jtc_settings(guild_id, user_id)
        primary_jtc_id = await _get_last_used_jtc_channel(guild_id, user_id)

        # Convert settings to response models with enriched names
        jtc_list = []
        for jtc_channel_id, settings in all_jtc_settings.items():
            # Helper to resolve target name and detect "everyone"
            def resolve_target(
                target_id: str, target_type: str
            ) -> tuple[str | None, bool, bool]:
                """Return (target_name, is_everyone, unknown_role)."""
                if target_id == "0":
                    return ("@everyone", True, False)
                if target_type == "role":
                    name = roles_map.get(target_id)
                    if name:
                        return (f"@{name}", False, False)
                    else:
                        return (None, False, True)  # Unknown role
                # User type
                return (None, False, False)  # Will be resolved async below

            # Normalize settings to ensure lists are present (not missing)
            permissions = []
            for p in settings.get("permissions", []):
                target_id = str(p[0])
                target_type = p[1]
                target_name, is_everyone, unknown_role = resolve_target(
                    target_id, target_type
                )
                # For users, fetch name asynchronously
                if target_type == "user" and not is_everyone:
                    target_name = await get_member_name(target_id)
                permissions.append(
                    PermissionEntry(
                        target_id=target_id,
                        target_type=target_type,
                        permission=p[2],
                        target_name=target_name,
                        is_everyone=is_everyone,
                        unknown_role=unknown_role,
                    )
                )

            ptt_settings = []
            for p in settings.get("ptt_settings", []):
                target_id = str(p[0])
                target_type = p[1]
                target_name, is_everyone, unknown_role = resolve_target(
                    target_id, target_type
                )
                if target_type == "user" and not is_everyone:
                    target_name = await get_member_name(target_id)
                ptt_settings.append(
                    PTTSettingEntry(
                        target_id=target_id,
                        target_type=target_type,
                        ptt_enabled=bool(p[2]),
                        target_name=target_name,
                        is_everyone=is_everyone,
                        unknown_role=unknown_role,
                    )
                )

            priority_settings = []
            for p in settings.get("priority_settings", []):
                target_id = str(p[0])
                target_type = p[1]
                target_name, is_everyone, unknown_role = resolve_target(
                    target_id, target_type
                )
                if target_type == "user" and not is_everyone:
                    target_name = await get_member_name(target_id)
                priority_settings.append(
                    PrioritySpeakerEntry(
                        target_id=target_id,
                        target_type=target_type,
                        priority_enabled=bool(p[2]),
                        target_name=target_name,
                        is_everyone=is_everyone,
                        unknown_role=unknown_role,
                    )
                )

            soundboard_settings = []
            for p in settings.get("soundboard_settings", []):
                target_id = str(p[0])
                target_type = p[1]
                target_name, is_everyone, unknown_role = resolve_target(
                    target_id, target_type
                )
                if target_type == "user" and not is_everyone:
                    target_name = await get_member_name(target_id)
                soundboard_settings.append(
                    SoundboardEntry(
                        target_id=target_id,
                        target_type=target_type,
                        soundboard_enabled=bool(p[2]),
                        target_name=target_name,
                        is_everyone=is_everyone,
                        unknown_role=unknown_role,
                    )
                )

            jtc_list.append(
                JTCChannelSettings(
                    jtc_channel_id=str(
                        jtc_channel_id
                    ),  # Convert to string to preserve precision in JSON/JS
                    channel_name=settings.get("channel_name"),
                    user_limit=settings.get("user_limit"),
                    lock=settings.get("lock", False),
                    permissions=permissions,
                    ptt_settings=ptt_settings,
                    priority_settings=priority_settings,
                    soundboard_settings=soundboard_settings,
                )
            )

        # Add user settings record (even if jtcs is empty)
        items.append(
            UserJTCSettings(
                user_id=str(
                    user_id
                ),  # Convert to string to preserve precision in JSON/JS
                rsi_handle=rsi_handle,
                community_moniker=community_moniker,
                primary_jtc_id=str(primary_jtc_id)
                if primary_jtc_id
                else None,  # Convert to string to preserve precision in JSON/JS
                jtcs=jtc_list,
            )
        )

    return VoiceUserSettingsSearchResponse(
        success=True,
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )
