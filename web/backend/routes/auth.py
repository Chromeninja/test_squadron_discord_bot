"""
Authentication routes for Discord OAuth2 flow.
"""

import logging
import os
import secrets
from pathlib import Path

import httpx
from core.dependencies import (
    ConfigLoader,
    InternalAPIClient,
    get_config_loader,
    get_internal_api_client,
    require_admin_or_moderator,
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
    SESSION_MAX_AGE,
    create_session_token,
    get_discord_authorize_url,
    set_session_cookie,
)
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse

router = APIRouter()
api_router = APIRouter()
logger = logging.getLogger(__name__)

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
    # Generate CSRF state token for OAuth security
    # TODO: Store state in session/redis and validate in callback for production security
    # See: https://datatracker.ietf.org/doc/html/rfc6749#section-10.12
    state = secrets.token_urlsafe(16)
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
        state: CSRF state token (not validated in MVP)

    Returns:
        Redirect to frontend with session cookie set
    """
    try:
        if not code:
            raise HTTPException(status_code=400, detail="Missing authorization code")

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
                    status_code=403,
                    detail="Unable to fetch guild memberships"
                )

            user_guilds = guilds_response.json()
            user_guild_ids = [g["id"] for g in user_guilds]

            print(f"User is member of guilds: {user_guild_ids}")

            # Get list of guilds where the bot is installed (from database)
            from services.db.database import Database
            from web.backend.core.guild_settings import get_bot_role_settings

            async with Database.get_connection() as db:
                cursor = await db.execute(
                    "SELECT DISTINCT guild_id FROM guild_settings"
                )
                rows = await cursor.fetchall()
                bot_guild_ids = {row[0] for row in rows}

            logger.debug(f"Bot is installed in guilds (from DB): {bot_guild_ids}")

            # Track authorization details for each guild
            authorized_guild_ids = []
            is_admin = False
            is_moderator = False
            permission_sources = {}  # guild_id -> permission source

            # Build a map of guild data for efficient lookup
            guild_data_map = {g["id"]: g for g in user_guilds}

            # Check ALL user guilds for Discord-native permissions (owner/administrator)
            # Then check database-registered guilds for role-based permissions
            for guild_id in user_guild_ids:
                try:
                    guild_data = guild_data_map.get(guild_id)
                    if not guild_data:
                        continue

                    # Check Discord-native permissions first (owner or administrator)
                    is_owner = guild_data.get("owner", False)
                    permissions_str = guild_data.get("permissions")
                    has_admin_permission = _has_administrator_permission(permissions_str)

                    logger.debug(f"Guild {guild_id}: owner={is_owner}, admin={has_admin_permission}")

                    # If user is guild owner or has administrator permission, grant admin access
                    if is_owner or has_admin_permission:
                        authorized_guild_ids.append(int(guild_id))
                        is_admin = True
                        permission_sources[int(guild_id)] = "owner" if is_owner else "administrator"
                        logger.info(f"User granted admin access to guild {guild_id} via {permission_sources[int(guild_id)]}")
                        continue  # Skip role-based check for performance

                    # Only check role-based permissions if guild is in the database
                    if int(guild_id) not in bot_guild_ids:
                        logger.debug(f"Guild {guild_id} not in bot database, skipping role-based check")
                        continue

                    # Fall back to role-based checking from database
                    guild_member_response = await client.get(
                        f"{DISCORD_API_BASE}/users/@me/guilds/{guild_id}/member",
                        headers={"Authorization": f"Bearer {access_token}"},
                    )

                    if guild_member_response.status_code == 429:
                        # Rate limited - skip remaining guilds
                        logger.warning(f"Rate limited while checking guild {guild_id}, skipping remaining guilds")
                        break

                    if guild_member_response.status_code != 200:
                        continue  # Skip guilds where we can't fetch member info

                    guild_member_data = guild_member_response.json()
                    user_role_ids = guild_member_data.get("roles", [])

                    # Check if user has admin/mod roles in this guild (from database)
                    async with Database.get_connection() as db:
                        role_settings = await get_bot_role_settings(db, int(guild_id))
                        bot_admin_role_ids = role_settings.get("bot_admins", [])
                        lead_moderator_role_ids = role_settings.get("lead_moderators", [])

                    # Convert user_role_ids to integers for comparison
                    user_role_ids_int = [int(rid) for rid in user_role_ids]

                    # Check if user has any admin/mod roles
                    has_admin_role = any(rid in bot_admin_role_ids for rid in user_role_ids_int)
                    has_mod_role = any(rid in lead_moderator_role_ids for rid in user_role_ids_int)

                    if has_admin_role or has_mod_role:
                        authorized_guild_ids.append(int(guild_id))
                        if has_admin_role:
                            is_admin = True
                            permission_sources[int(guild_id)] = "bot_admin_role"
                        if has_mod_role:
                            is_moderator = True
                            permission_sources[int(guild_id)] = "moderator_role"
                        logger.info(f"User granted access to guild {guild_id} via {permission_sources[int(guild_id)]}")

                except Exception as e:
                    print(f"Error checking roles for guild {guild_id}: {e}")
                    continue

        # Extract user information
        user_id = user_data.get("id")
        username = user_data.get("username", "Unknown")
        discriminator = user_data.get("discriminator", "0")
        avatar = user_data.get("avatar")

        if not user_id:
            raise HTTPException(status_code=400, detail="Invalid user data")

        # Debug logging
        logger.info(f"User {user_id} authorized for {len(authorized_guild_ids)} guild(s)")
        logger.debug(f"Authorized guild IDs: {authorized_guild_ids}")
        logger.debug(f"is_admin: {is_admin}, is_moderator: {is_moderator}")
        logger.debug(f"Permission sources: {permission_sources}")

        # Require at least one authorized guild
        if not authorized_guild_ids:
            # Return unauthorized page
            return Response(
                content="""
                <!DOCTYPE html>
                <html>
                <head><title>Access Denied</title></head>
                <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                    <h1>Access Denied</h1>
                    <p>You do not have bot admin or moderator roles in any server where this bot is installed.</p>
                    <p>Contact a bot administrator if you believe this is an error.</p>
                </body>
                </html>
                """,
                media_type="text/html",
                status_code=403,
            )

        # Create session token with authorized guild IDs and permission sources
        # Convert permission_sources keys to strings for JSON/JWT serialization
        permission_sources_str = {str(k): v for k, v in permission_sources.items()}

        # Do NOT auto-select guild - force user to choose from SelectServer screen
        # This ensures users explicitly select which server to manage
        logger.info(f"User {user_id} authorized for {len(authorized_guild_ids)} guild(s), redirecting to guild selection")

        session_data = {
            "user_id": user_id,
            "username": username,
            "discriminator": discriminator,
            "avatar": avatar,
            "is_admin": is_admin,
            "is_moderator": is_moderator,
            "authorized_guild_ids": authorized_guild_ids,
            "active_guild_id": None,  # Null to trigger SelectServer screen
            "permission_sources": permission_sources_str,  # Store for debugging/audit
        }

        session_token = create_session_token(session_data)

        # Create response with session cookie
        response = RedirectResponse(url="http://localhost:5173")
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=session_token,
            max_age=SESSION_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=False,  # Set to True in production with HTTPS
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"Error in OAuth callback: {e}")
        print(traceback.format_exc())
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
    current_user: UserProfile = Depends(require_admin_or_moderator),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Return guilds where:
    1. The bot is currently installed (from internal API)
    2. The user has admin/moderator permissions (from authorized_guild_ids)
    
    This ensures users only see guilds they can manage and where the bot is active.
    """
    try:
        guilds = await internal_api.get_guilds()
    except Exception as exc:  # pragma: no cover - transport errors
        raise translate_internal_api_error(exc, "Failed to fetch guilds") from exc

    # Get user's authorized guild IDs from session - convert to strings for comparison
    authorized_guild_ids = set(str(gid) for gid in (current_user.authorized_guild_ids or []))

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

    logger.info(f"Returning {len(summaries)} guild(s) to user")
    return GuildListResponse(guilds=summaries)



@api_router.post("/select-guild", response_model=SelectGuildResponse)
async def select_active_guild(
    payload: SelectGuildRequest,
    response: Response,
    current_user: UserProfile = Depends(require_admin_or_moderator),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """Persist the active guild in the session cookie."""
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

    session_payload = current_user.dict()
    session_payload["active_guild_id"] = payload.guild_id
    set_session_cookie(response, session_payload)

    return SelectGuildResponse()


@api_router.post("/logout")
async def logout(response: Response):
    """
    Logout user by clearing session cookie.

    Returns:
        Success response
    """
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return {"success": True, "message": "Logged out successfully"}


@api_router.get("/bot-invite-url")
async def get_bot_invite_url(
    config_loader: ConfigLoader = Depends(get_config_loader),
):
    """
    Get Discord bot authorization URL for inviting bot to a server.
    
    Uses bot permissions from config and sets redirect URI to bot callback endpoint.
    
    Returns:
        JSON with invite_url field
    """
    # Load config path relative to project root
    project_root = Path(__file__).parent.parent.parent.parent
    config_path = project_root / "config" / "config.yaml"

    # Load config using ConfigLoader class method
    config_dict = ConfigLoader.load_config(str(config_path))
    bot_permissions = config_dict.get("discord", {}).get("bot_permissions", 8)

    # Build bot invite URL with redirect back to our callback
    bot_redirect_uri = os.getenv(
        "DISCORD_BOT_REDIRECT_URI",
        "http://localhost:8081/auth/bot-callback"
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
            url=f"http://localhost:5173/select-server?error={error}",
            status_code=302,
        )

    # Success - redirect to SelectServer page
    # Frontend will automatically refresh the guild list
    logger.info(f"Bot successfully added to guild {guild_id}")
    return RedirectResponse(
        url="http://localhost:5173/select-server?bot_added=true",
        status_code=302,
    )


@api_router.delete("/active-guild")
async def clear_active_guild(
    response: Response,
    current_user: UserProfile = Depends(require_admin_or_moderator),
):
    """
    Clear the active guild from session, forcing user to SelectServer screen.
    
    Used by 'Switch Server' button in dashboard.
    
    Returns:
        Success response
    """
    session_payload = current_user.dict()
    session_payload["active_guild_id"] = None
    set_session_cookie(response, session_payload)

    return {"success": True}
