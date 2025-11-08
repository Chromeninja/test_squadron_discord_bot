"""
Authentication routes for Discord OAuth2 flow.
"""

import secrets

import httpx
from fastapi import APIRouter, Cookie, HTTPException, Response
from fastapi.responses import RedirectResponse

from core.dependencies import get_config_loader, get_current_user
from core.schemas import AuthMeResponse, ErrorResponse, UserProfile
from core.security import (
    DISCORD_API_BASE,
    DISCORD_CLIENT_ID,
    DISCORD_CLIENT_SECRET,
    DISCORD_GUILD_ID,
    DISCORD_REDIRECT_URI,
    DISCORD_TOKEN_URL,
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE,
    check_user_has_roles,
    create_session_token,
    get_discord_authorize_url,
)

router = APIRouter()
api_router = APIRouter()


@router.get("/login")
async def login():
    """
    Initiate Discord OAuth2 flow.

    Redirects user to Discord authorization page.
    """
    # Generate CSRF state token (optional but recommended)
    state = secrets.token_urlsafe(16)
    auth_url = get_discord_authorize_url(state)

    # In production, store state in session/redis for validation
    # For MVP, we'll skip state validation

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

            # Fetch user's guild member info to get roles
            guild_member_response = await client.get(
                f"{DISCORD_API_BASE}/users/@me/guilds/{DISCORD_GUILD_ID}/member",
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if guild_member_response.status_code != 200:
                raise HTTPException(
                    status_code=403,
                    detail="Unable to verify guild membership. Please ensure you're a member of the Discord server."
                )

            guild_member_data = guild_member_response.json()
            user_role_ids = guild_member_data.get("roles", [])

        # Extract user information
        user_id = user_data.get("id")
        username = user_data.get("username", "Unknown")
        discriminator = user_data.get("discriminator", "0")
        avatar = user_data.get("avatar")

        if not user_id:
            raise HTTPException(status_code=400, detail="Invalid user data")

        # Check authorization against config
        config_loader = get_config_loader()
        # ConfigLoader stores config in _config class variable after load_config()
        config = config_loader._config

        bot_admin_role_ids = config.get("roles", {}).get("bot_admins", [])
        lead_moderator_role_ids = config.get("roles", {}).get("lead_moderators", [])

        # Debug logging
        print(f"User ID from Discord: {user_id} (type: {type(user_id)})")
        print(f"User role IDs: {user_role_ids}")
        print(f"Bot admin role IDs from config: {bot_admin_role_ids}")
        print(f"Lead moderator role IDs from config: {lead_moderator_role_ids}")

        is_admin, is_moderator = check_user_has_roles(
            user_role_ids, bot_admin_role_ids, lead_moderator_role_ids
        )

        print(f"Authorization result - is_admin: {is_admin}, is_moderator: {is_moderator}")


        # Require at least one role
        if not (is_admin or is_moderator):
            # Return unauthorized page
            return Response(
                content="""
                <!DOCTYPE html>
                <html>
                <head><title>Access Denied</title></head>
                <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                    <h1>Access Denied</h1>
                    <p>You do not have permission to access this dashboard.</p>
                    <p>Contact a bot administrator if you believe this is an error.</p>
                </body>
                </html>
                """,
                media_type="text/html",
                status_code=403,
            )

        # Create session token
        session_data = {
            "user_id": user_id,
            "username": username,
            "discriminator": discriminator,
            "avatar": avatar,
            "is_admin": is_admin,
            "is_moderator": is_moderator,
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
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


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


@api_router.post("/logout")
async def logout(response: Response):
    """
    Logout user by clearing session cookie.

    Returns:
        Success response
    """
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return {"success": True, "message": "Logged out successfully"}
