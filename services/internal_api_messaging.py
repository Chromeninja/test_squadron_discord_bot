"""Channel-messaging routes for the internal API.

Kept out of services/internal_api.py (a legacy monolith with a recorded
modularity ceiling) so the event-coordinator messaging feature does not grow
that file. Handlers here follow the same auth and response conventions as
InternalAPIServer.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from aiohttp import web

if TYPE_CHECKING:
    from services.internal_api import InternalAPIServer

logger = logging.getLogger(__name__)


def register_messaging_routes(app: web.Application, server: InternalAPIServer) -> None:
    """Attach channel-messaging routes to the internal API app."""

    async def _send(request: web.Request) -> web.Response:
        return await handle_send_channel_message(server, request)

    app.router.add_post("/guilds/{guild_id}/channels/{channel_id}/message", _send)


async def handle_send_channel_message(
    server: Any, request: web.Request
) -> web.Response:
    """Send a message (with optional user mentions) to a guild channel.

    Body JSON: {"message": str, "user_ids": [str, ...] (optional)}
    Used by the dashboard for coordinator event messaging. Validates the
    bot can send to the channel before posting. Does not DM users.
    """
    if not server._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    if not server.bot:
        return web.json_response({"error": "Bot unavailable"}, status=503)

    try:
        guild_id = int(request.match_info.get("guild_id", "0"))
        channel_id = int(request.match_info.get("channel_id", "0"))
    except (TypeError, ValueError):
        return web.json_response({"error": "Invalid guild or channel id"}, status=400)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    message = str(body.get("message") or "").strip()
    if not message:
        return web.json_response({"error": "Message is required"}, status=400)

    user_ids_raw = body.get("user_ids") or []
    user_ids: list[str] = []
    if isinstance(user_ids_raw, list):
        user_ids = [str(uid) for uid in user_ids_raw if str(uid).strip()]

    guild = server.bot.get_guild(guild_id)
    if guild is None:
        return web.json_response({"error": "Guild not found"}, status=404)

    import discord

    channel = guild.get_channel(channel_id)
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        return web.json_response(
            {"error": "Channel not found or not a text channel"}, status=404
        )

    me = guild.me
    if me is not None:
        perms = channel.permissions_for(me)
        if not perms.send_messages:
            return web.json_response(
                {"error": "Bot cannot send messages to this channel"}, status=403
            )

    content = message
    if user_ids:
        mentions = " ".join(f"<@{uid}>" for uid in user_ids)
        content = f"{message}\n\n{mentions}"

    # Discord hard-limits message content to 2000 characters.
    if len(content) > 2000:
        content = content[:2000]

    try:
        await channel.send(
            content,
            allowed_mentions=discord.AllowedMentions(
                users=True, roles=False, everyone=False
            ),
        )
    except Exception as exc:  # pragma: no cover - runtime safeguard
        logger.exception(
            "Failed to send channel message to channel %s in guild %s",
            channel_id,
            guild_id,
            exc_info=exc,
        )
        return web.json_response({"error": "Failed to send message"}, status=500)

    return web.json_response({"success": True, "recipients": len(user_ids)})
