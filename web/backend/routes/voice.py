"""
Voice channel search endpoints.
"""

import json
import os

import httpx
from core.dependencies import get_db, require_admin_or_moderator
from core.guild_settings import get_organization_settings
from core.schemas import (
    ActiveVoiceChannel,
    ActiveVoiceChannelsResponse,
    UserProfile,
    VoiceChannelRecord,
    VoiceSearchResponse,
)
from fastapi import APIRouter, Depends, Query

router = APIRouter()

# Discord API configuration
DISCORD_BOT_TOKEN = os.getenv("DISCORD_TOKEN", "")
DISCORD_API_BASE = "https://discord.com/api/v10"

# Internal API configuration (bot-to-web communication)
# This points to the bot's internal API server (no Discord API calls)
INTERNAL_API_URL = os.getenv("INTERNAL_API_URL", "http://127.0.0.1:8082")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "dev_internal_api_key_change_in_production")



@router.get("/active", response_model=ActiveVoiceChannelsResponse)
async def list_active_voice_channels(
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_admin_or_moderator),
):
    """
    List all active voice channels with owner information and current members.

    Returns active voice channels with real-time member data from Discord API.

    Requires: Admin or moderator role

    Returns:
        ActiveVoiceChannelsResponse with active channel list
    """
    # Query active voice channels with owner verification info
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
        ORDER BY vc.last_activity DESC
        """,
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
            organization_sid = org_settings.get("organization_sid") if org_settings else None
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
                        print(f"Internal API returned {internal_response.status_code} for channel {voice_channel_id}")
                        # Fall back to just showing owner
                        member_ids = [owner_id]
                except Exception as e:
                    print(f"Error querying internal API for channel {voice_channel_id}: {e}")
                    # Fall back to just showing owner
                    member_ids = [owner_id]

                # Ensure owner is always in the list
                if owner_id not in member_ids:
                    member_ids.append(owner_id)

                # Get verification info for members (status derived from org lists)
                members_in_channel = []
                if member_ids:
                    placeholders = ','.join('?' * len(member_ids))
                    members_cursor = await db.execute(
                        f"""
                        SELECT user_id, rsi_handle, main_orgs, affiliate_orgs
                        FROM verification
                        WHERE user_id IN ({placeholders})
                        """,
                        tuple(member_ids)
                    )
                    fetched = await members_cursor.fetchall()
                    verification_data = {r[0]: {
                        'rsi_handle': r[1],
                        'main_orgs': json.loads(r[2]) if r[2] else None,
                        'affiliate_orgs': json.loads(r[3]) if r[3] else None
                    } for r in fetched}

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
                                username = user_data.get('username')
                        except:
                            pass

                        members_in_channel.append({
                            "user_id": user_id,
                            "username": username,
                            "display_name": verification.get('rsi_handle') or username or f"User {user_id}",
                            "rsi_handle": verification.get('rsi_handle'),
                            "membership_status": _derive(verification.get('main_orgs'), verification.get('affiliate_orgs'), organization_sid),
                            "is_owner": user_id == owner_id,
                        })

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
                print(f"Error fetching Discord data for channel {voice_channel_id}: {e}")
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
