"""
Authentication routes for Discord OAuth2 flow.
"""

import logging
import os

import httpx
from core.dependencies import (
    ConfigLoader,
    InternalAPIClient,
    get_config_loader,
    get_internal_api_client,
    require_any_guild_access,
    require_is_bot_owner,
    translate_internal_api_error,
)
from core.schemas import (
    AuthMeResponse,
    GuildListResponse,
    GuildSummary,
    SelectGuildRequest,
    SelectGuildResponse,
    UserProfile,
)
from core.security import (
    DISCORD_API_BASE,
    DISCORD_CLIENT_ID,
    DISCORD_CLIENT_SECRET,
    DISCORD_OAUTH_URL,
    DISCORD_REDIRECT_URI,
    DISCORD_TOKEN_URL,
    SESSION_COOKIE_NAME,
    clear_session_cookie,
    generate_oauth_state,
    get_discord_authorize_url,
    set_session_cookie,
    validate_oauth_state,
)
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

router = APIRouter()
api_router = APIRouter()
logger = logging.getLogger(__name__)

# Frontend URL for redirects (defaults to dev server if not set)
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# Discord permission bitfield for Administrator
ADMINISTRATOR_PERMISSION = 0x0000000000000008


def _normalize_guild_id(raw_value) -> str | None:
    """Convert guild IDs from the internal API into canonical string form."""
    if raw_value is None:
        return None
    try:
        return str(int(raw_value))
    except (TypeError, ValueError):
        return None


def _has_administrator_permission(permissions_str: str | None) -> bool:
    """Check if user has Discord administrator permission from bitfield.

    Args:
        permissions_str: Permission bitfield as string from Discord API

    Returns:
        True if user has administrator permission (0x8 bit set)
    """
    if not permissions_str:
        return False
    try:
        permissions = int(permissions_str)
        return (permissions & ADMINISTRATOR_PERMISSION) != 0
    except (ValueError, TypeError):
        return False


@router.get("/login")
async def login():
    """
    Initiate Discord OAuth2 flow.

    Redirects user to Discord authorization page.
    """
    # Generate CSRF state token for OAuth security (stored in-memory, validated in callback)
    state = generate_oauth_state()
    auth_url = get_discord_authorize_url(state)

    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def callback(code: str, state: str | None = None):
    """
    Handle Discord OAuth2 callback.

    Exchanges authorization code for access token,
    fetches user info, checks authorization, and sets session cookie.

    Args:
        code: Authorization code from Discord
        state: CSRF state token (validated against stored state)

    Returns:
        Redirect to frontend with session cookie set
    """
    try:
        if not code:
            raise HTTPException(status_code=400, detail="Missing authorization code")

        # Validate CSRF state token (one-time use, expires after 5 minutes)
        if not state or not validate_oauth_state(state):
            logger.warning("OAuth callback with invalid or expired state token")
            raise HTTPException(status_code=400, detail="Invalid or expired state token")

        # Exchange code for access token
        async with httpx.AsyncClient() as client:
            token_data = {
                "client_id": DISCORD_CLIENT_ID,
                "client_secret": DISCORD_CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": DISCORD_REDIRECT_URI,
            }

            token_response = await client.post(
                DISCORD_TOKEN_URL,
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if token_response.status_code != 200:
                raise HTTPException(
                    status_code=400,
                    detail="Failed to exchange authorization code",
                )

            token_json = token_response.json()
            access_token = token_json.get("access_token")

            if not access_token:
                raise HTTPException(status_code=400, detail="No access token received")

            # Fetch user information
            user_response = await client.get(
                f"{DISCORD_API_BASE}/users/@me",
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if user_response.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to fetch user info")

            user_data = user_response.json()

            # Fetch user's guilds to check membership and roles across all guilds
            guilds_response = await client.get(
                f"{DISCORD_API_BASE}/users/@me/guilds",
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if guilds_response.status_code != 200:
                raise HTTPException(
                    status_code=403, detail="Unable to fetch guild memberships"
                )

            user_guilds = guilds_response.json()
            user_guild_ids = [g["id"] for g in user_guilds]

            logger.debug(
                "OAuth user is member of %d guild(s)", len(user_guild_ids)
            )

            # Get list of guilds where the bot is installed (from database)
            from services.db.repository import BaseRepository
            from web.backend.core.guild_settings import fetch_bot_role_settings

            rows = await BaseRepository.fetch_all(
                "SELECT DISTINCT guild_id FROM guild_settings"
            )
            bot_guild_ids = {row[0] for row in rows}

            logger.debug(f"Bot is installed in guilds (from DB): {bot_guild_ids}")

            # Check if user is bot owner (global permission) via internal API
            # This supports single owner, team owners, and env overrides
            user_id_from_data = user_data.get("id")
            is_bot_owner = False

            try:
                internal_api = InternalAPIClient()
                bot_owner_ids = await internal_api.get_bot_owner_ids()
                await internal_api.close()
                is_bot_owner = int(user_id_from_data) in bot_owner_ids
            except Exception as e:
                # Fallback to env var if internal API is unavailable
                logger.warning(f"Could not fetch bot owner IDs from internal API: {e}")
                env_owner_id = os.getenv("BOT_OWNER_ID")
                env_owner_ids = os.getenv("BOT_OWNER_IDS", "")
                owner_ids_set: set[int] = set()
                if env_owner_id:
                    try:
                        owner_ids_set.add(int(env_owner_id))
                    except ValueError:
                        pass
                for id_str in env_owner_ids.split(","):
                    id_str = id_str.strip()
                    if id_str:
                        try:
                            owner_ids_set.add(int(id_str))
                        except ValueError:
                            pass
                is_bot_owner = int(user_id_from_data) in owner_ids_set

            if is_bot_owner:
                logger.info(
                    f"User {user_id_from_data} identified as BOT OWNER - granting global access"
                )

            # Track per-guild permissions using new GuildPermission model
            from core.schemas import GuildPermission

            authorized_guilds: dict[str, GuildPermission] = {}
            authorized_guild_id_set: set[str] = set()

            # Build a map of guild data for efficient lookup
            guild_data_map = {g["id"]: g for g in user_guilds}

            # Check ALL user guilds for permissions
            for guild_id in user_guild_ids:
                try:
                    guild_data = guild_data_map.get(guild_id)
                    if not guild_data:
                        continue

                    # Bot owner gets full access to ALL guilds
                    if is_bot_owner:
                        guild_id_str = str(guild_id)
                        authorized_guilds[guild_id_str] = GuildPermission(
                            guild_id=guild_id_str,
                            role_level="bot_owner",
                            source="bot_owner",
                        )
                        authorized_guild_id_set.add(guild_id_str)
                        continue

                    # Check Discord-native permissions (owner or administrator)
                    is_owner = guild_data.get("owner", False)
                    permissions_str = guild_data.get("permissions")
                    has_admin_permission = _has_administrator_permission(
                        permissions_str
                    )

                    logger.debug(
                        f"Guild {guild_id}: owner={is_owner}, admin={has_admin_permission}"
                    )

                    # Guild owner gets bot_admin level
                    if is_owner:
                        guild_id_str = str(guild_id)
                        authorized_guilds[guild_id_str] = GuildPermission(
                            guild_id=guild_id_str,
                            role_level="bot_admin",
                            source="discord_owner",
                        )
                        authorized_guild_id_set.add(guild_id_str)
                        logger.info(
                            f"User granted bot_admin access to guild {guild_id} via discord_owner"
                        )
                        continue

                    # Discord administrator permission gets bot_admin level
                    if has_admin_permission:
                        guild_id_str = str(guild_id)
                        authorized_guilds[guild_id_str] = GuildPermission(
                            guild_id=guild_id_str,
                            role_level="bot_admin",
                            source="discord_administrator",
                        )
                        authorized_guild_id_set.add(guild_id_str)
                        logger.info(
                            f"User granted bot_admin access to guild {guild_id} via discord_administrator"
                        )
                        continue

                    # Only check role-based permissions if guild is in the database
                    if int(guild_id) not in bot_guild_ids:
                        logger.debug(
                            f"Guild {guild_id} not in bot database, skipping role-based check"
                        )
                        continue

                    # Fetch guild member info for role checking
                    guild_member_response = await client.get(
                        f"{DISCORD_API_BASE}/users/@me/guilds/{guild_id}/member",
                        headers={"Authorization": f"Bearer {access_token}"},
                    )

                    if guild_member_response.status_code == 429:
                        logger.warning(
                            f"Rate limited while checking guild {guild_id}, skipping remaining guilds"
                        )
                        break

                    if guild_member_response.status_code != 200:
                        continue

                    guild_member_data = guild_member_response.json()
                    user_role_ids = guild_member_data.get("roles", [])

                    # Fetch role configuration from database
                    role_settings = await fetch_bot_role_settings(int(guild_id))
                    bot_admin_role_ids = [
                        int(rid) for rid in role_settings.get("bot_admins", [])
                    ]
                    discord_manager_role_ids = [
                        int(rid)
                        for rid in role_settings.get("discord_managers", [])
                    ]
                    moderator_role_ids = [
                        int(rid) for rid in role_settings.get("moderators", [])
                    ]
                    staff_role_ids = [
                        int(rid) for rid in role_settings.get("staff", [])
                    ]

                    # Convert user_role_ids to integers
                    user_role_ids_int = [int(rid) for rid in user_role_ids]

                    # Determine highest role level (check in hierarchy order)
                    role_level = None
                    source = None

                    if any(rid in bot_admin_role_ids for rid in user_role_ids_int):
                        role_level = "bot_admin"
                        source = "bot_admin_role"
                    elif any(
                        rid in discord_manager_role_ids for rid in user_role_ids_int
                    ):
                        role_level = "discord_manager"
                        source = "discord_manager_role"
                    elif any(rid in moderator_role_ids for rid in user_role_ids_int):
                        role_level = "moderator"
                        source = "moderator_role"
                    elif any(rid in staff_role_ids for rid in user_role_ids_int):
                        role_level = "staff"
                        source = "staff_role"

                    if role_level and source:
                        guild_id_str = str(guild_id)
                        authorized_guilds[guild_id_str] = GuildPermission(
                            guild_id=guild_id_str, role_level=role_level, source=source
                        )
                        authorized_guild_id_set.add(guild_id_str)
                        logger.info(
                            f"User granted {role_level} access to guild {guild_id} via {source}"
                        )

                except Exception:
                    logger.exception(
                        "Error checking roles for guild %s during OAuth role evaluation",
                        guild_id,
                    )
                    continue

        # Extract user information
        user_id = user_data.get("id")
        username = user_data.get("username", "Unknown")
        discriminator = user_data.get("discriminator", "0")
        avatar = user_data.get("avatar")

        if not user_id:
            raise HTTPException(status_code=400, detail="Invalid user data")

        # Debug logging
        logger.info(f"User {user_id} authorized for {len(authorized_guilds)} guild(s)")
        logger.debug(f"Authorized guild IDs: {sorted(authorized_guild_id_set)}")
        logger.debug(
            f"Per-guild permissions: {[(g, p.role_level) for g, p in authorized_guilds.items()]}"
        )

        # Require at least one authorized guild
        if not authorized_guilds:
            # Return unauthorized page
            return Response(
                content="""
                <!DOCTYPE html>
                <html>
                <head><title>Access Denied</title></head>
                <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                    <h1>Access Denied</h1>
                    <p>You do not have permission roles in any server where this bot is installed.</p>
                    <p>Contact a bot administrator if you believe this is an error.</p>
                </body>
                </html>
                """,
                media_type="text/html",
                status_code=403,
            )

        # Convert authorized_guilds to serializable dict for JWT
        authorized_guilds_dict = {
            guild_id: {
                "guild_id": perm.guild_id,
                "role_level": perm.role_level,
                "source": perm.source,
            }
            for guild_id, perm in authorized_guilds.items()
        }

        # Do NOT auto-select guild - force user to choose from SelectServer screen
        logger.info(
            f"User {user_id} authorized for {len(authorized_guilds)} guild(s), redirecting to guild selection"
        )

        session_data = {
            "user_id": user_id,
            "username": username,
            "discriminator": discriminator,
            "avatar": avatar,
            "authorized_guilds": authorized_guilds_dict,
            "active_guild_id": None,  # Null to trigger SelectServer screen
            "roles_validated_at": {},  # Per-guild validation timestamps
            "is_bot_owner": is_bot_owner,  # Global bot owner flag
        }

        # Create response with session cookie using centralized helper
        response = RedirectResponse(url=FRONTEND_URL)
        set_session_cookie(response, session_data)
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in OAuth callback")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e!s}")


@api_router.get("/me", response_model=AuthMeResponse)
async def get_me(session: str | None = Cookie(None, alias=SESSION_COOKIE_NAME)):
    """
    Get current authenticated user profile.

    Requires valid session cookie.

    Returns:
        AuthMeResponse with user profile or None if not authenticated
    """
    if not session:
        return AuthMeResponse(success=True, user=None)

    from core.security import decode_session_token

    user_data = decode_session_token(session)
    if not user_data:
        return AuthMeResponse(success=True, user=None)

    user = UserProfile(**user_data)
    return AuthMeResponse(success=True, user=user)


@api_router.get("/guilds", response_model=GuildListResponse)
async def get_available_guilds(
    current_user: UserProfile = Depends(require_any_guild_access),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Return guilds where the bot is installed and the user has permission.

    This ensures users only see guilds they can manage and where the bot is active.
    """
    logger.info(
        "Guild list requested",
        extra={
            "user_id": current_user.user_id,
            "authorized_guilds": list(current_user.authorized_guilds.keys()),
        },
    )
    try:
        guilds = await internal_api.get_guilds()
    except Exception as exc:  # pragma: no cover - transport errors
        logger.warning(
            "Internal API guild fetch failed; falling back to session guilds",
            exc_info=exc,
            extra={
                "user_id": current_user.user_id,
                "authorized_guild_count": len(current_user.authorized_guilds),
            },
        )
        guilds = [
            {
                "guild_id": gid,
                "guild_name": f"Guild {gid}",
                "icon_url": None,
            }
            for gid in current_user.authorized_guilds
        ]

        if not guilds:
            # Preserve previous behavior: surface the original failure when we have no fallback data
            raise translate_internal_api_error(exc, "Failed to fetch guilds") from exc

    # Build set of authorized guild IDs (string form) sourced from the session payload
    authorized_guild_ids = set(current_user.authorized_guilds)

    logger.debug(f"Bot guilds from internal API: {[g.get('guild_id') for g in guilds]}")
    logger.debug(f"User authorized guild IDs: {authorized_guild_ids}")

    summaries = []
    for guild in guilds:
        normalized_id = _normalize_guild_id(guild.get("guild_id"))
        if normalized_id is None:
            continue

        # Only include guilds where user has admin/moderator permissions
        if normalized_id not in authorized_guild_ids:
            logger.debug(f"Skipping guild {normalized_id} - not in authorized list")
            continue

        logger.debug(f"Including guild {normalized_id} - {guild.get('guild_name')}")
        summaries.append(
            GuildSummary(
                guild_id=normalized_id,
                guild_name=guild.get("guild_name", "Unnamed Guild"),
                icon_url=guild.get("icon_url"),
            )
        )

    logger.info(
        "Guild list response",
        extra={
            "user_id": current_user.user_id,
            "returned": len(summaries),
            "authorized": len(authorized_guild_ids),
        },
    )
    return GuildListResponse(guilds=summaries)


class AllGuildsMetadataResponse(BaseModel):
    """Response for /api/auth/all-guilds-metadata endpoint (bot owner only)."""

    success: bool = True
    guilds: dict[str, GuildSummary]  # guild_id -> GuildSummary map for fast lookup


@api_router.get("/all-guilds-metadata", response_model=AllGuildsMetadataResponse)
async def get_all_guilds_metadata(
    current_user: UserProfile = Depends(require_is_bot_owner),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """Get metadata for all guilds where the bot is installed.

    Bot owner only - designed for client-side caching of guild labels
    when viewing cross-guild data.

    Returns a map of guild_id -> GuildSummary for fast lookup.
    """
    try:
        guilds = await internal_api.get_guilds()
    except Exception as exc:
        raise translate_internal_api_error(exc, "Failed to fetch guilds") from exc

    guild_map = {}
    for guild in guilds:
        normalized_id = _normalize_guild_id(guild.get("guild_id"))
        if normalized_id is None:
            continue

        guild_map[normalized_id] = GuildSummary(
            guild_id=normalized_id,
            guild_name=guild.get("guild_name", "Unnamed Guild"),
            icon_url=guild.get("icon_url"),
        )

    logger.info(
        "All guilds metadata requested by bot owner",
        extra={"user_id": current_user.user_id, "guild_count": len(guild_map)},
    )

    return AllGuildsMetadataResponse(guilds=guild_map)


@api_router.post("/select-guild", response_model=SelectGuildResponse)
async def select_active_guild(
    payload: SelectGuildRequest,
    response: Response,
    current_user: UserProfile = Depends(require_any_guild_access),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """Persist the active guild in the session cookie.

    Special case: Bot owners can select guild_id="*" (ALL_GUILDS_SENTINEL)
    to enter "All Guilds" cross-guild view mode.
    """
    from core.pagination import ALL_GUILDS_SENTINEL

    # Allow bot owners to select "All Guilds" mode
    if payload.guild_id == ALL_GUILDS_SENTINEL:
        if not current_user.is_bot_owner:
            raise HTTPException(
                status_code=403,
                detail="All Guilds mode is only available to bot owners",
            )
        # Set active_guild_id to sentinel and return early
        session_payload = current_user.model_dump()
        session_payload["active_guild_id"] = ALL_GUILDS_SENTINEL
        set_session_cookie(response, session_payload)
        logger.info(
            "Bot owner entered All Guilds mode",
            extra={"user_id": current_user.user_id},
        )
        return SelectGuildResponse()

    try:
        guilds = await internal_api.get_guilds()
    except Exception as exc:  # pragma: no cover - transport errors
        raise translate_internal_api_error(exc, "Failed to fetch guilds") from exc

    allowed_ids: set[str] = set()
    for guild in guilds:
        normalized = _normalize_guild_id(guild.get("guild_id"))
        if normalized:
            allowed_ids.add(normalized)

    if not allowed_ids:
        logger.warning(
            "internal API returned no guilds during selection; accepting guild_id=%s",
            payload.guild_id,
        )
    elif payload.guild_id not in allowed_ids:
        raise HTTPException(status_code=404, detail="Guild not found")

    # Rebuild session payload, initializing/refreshing validation timestamp for the chosen guild
    session_payload = current_user.model_dump()
    session_payload["active_guild_id"] = payload.guild_id
    roles_validated_at = session_payload.get("roles_validated_at") or {}
    import time as _t

    roles_validated_at[payload.guild_id] = int(_t.time())
    session_payload["roles_validated_at"] = roles_validated_at
    set_session_cookie(response, session_payload)

    return SelectGuildResponse()


@api_router.post("/logout")
async def logout(response: Response):
    """Logout user by clearing the session cookie."""
    clear_session_cookie(response)
    return {"success": True, "message": "Logged out successfully"}


@api_router.get("/bot-invite-url")
async def get_bot_invite_url(
    current_user: UserProfile = Depends(require_is_bot_owner),
    config_loader: ConfigLoader = Depends(get_config_loader),
):
    """
    Get Discord bot authorization URL for inviting bot to a server.

    Bot owner only - uses bot permissions from config and sets redirect URI to bot callback endpoint.

    Returns:
        JSON with invite_url field
    """
    # Use centralized ConfigLoader (already initialized at startup)
    config_dict = config_loader.load_config()
    bot_permissions = config_dict.get("discord", {}).get("bot_permissions", 8)

    # Build bot invite URL with redirect back to our callback
    bot_redirect_uri = os.getenv(
        "DISCORD_BOT_REDIRECT_URI", "http://localhost:8081/auth/bot-callback"
    )

    from urllib.parse import urlencode

    params = {
        "client_id": DISCORD_CLIENT_ID,
        "permissions": str(bot_permissions),
        "scope": "bot applications.commands",
        "redirect_uri": bot_redirect_uri,
    }

    invite_url = f"{DISCORD_OAUTH_URL}?{urlencode(params)}"

    return {"invite_url": invite_url}


@router.get("/bot-callback")
async def bot_authorization_callback(
    guild_id: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    """
    Handle Discord redirect after bot authorization.

    Discord redirects here after user adds bot to a server.
    We redirect user back to the frontend SelectServer page.

    Query params:
        guild_id: Guild where bot was added (if successful)
        error: Error code if authorization failed
        error_description: Human-readable error description

    Returns:
        Redirect to frontend SelectServer page
    """
    # Check for errors
    if error:
        logger.warning(f"Bot authorization failed: {error} - {error_description}")
        # Redirect to frontend with error
        return RedirectResponse(
            url=f"{FRONTEND_URL}/select-server?error={error}",
            status_code=302,
        )

    # Success - redirect to SelectServer page
    # Frontend will automatically refresh the guild list
    logger.info(f"Bot successfully added to guild {guild_id}")
    return RedirectResponse(
        url=f"{FRONTEND_URL}/select-server?bot_added=true",
        status_code=302,
    )


@api_router.delete("/active-guild")
async def clear_active_guild(
    response: Response,
    current_user: UserProfile = Depends(require_any_guild_access),
):
    """
    Clear the active guild from session, forcing user to SelectServer screen.

    Used by 'Switch Server' button in dashboard.

    Returns:
        Success response
    """
    session_payload = current_user.model_dump()
    session_payload["active_guild_id"] = None
    set_session_cookie(response, session_payload)

    return {"success": True}
