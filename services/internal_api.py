"""
Internal API server for bot-to-web communication.

Provides HTTP endpoints for the web dashboard to query bot state
without hitting Discord API rate limits.
"""

import base64
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from aiohttp import web

from helpers.announcement import send_admin_bulk_check_summary
from helpers.bulk_check import StatusRow, build_summary_embed
from helpers.leadership_log import InitiatorKind, InitiatorSource
from services.db.repository import BaseRepository
from utils.logging import get_logger

if TYPE_CHECKING:
    from bot import MyBot
    from services.service_container import ServiceContainer

logger = get_logger(__name__)


class InternalAPIServer:
    """
    Lightweight internal HTTP server for exposing bot state to web dashboard.

    This server runs alongside the Discord bot and provides endpoints that
    the web backend can query for real-time data without Discord API calls.
    """

    def __init__(self, services: "ServiceContainer"):
        self.services = services
        # Store bot reference for easy access
        self.bot = services.bot
        self.app = web.Application()
        self.runner = None
        self.site = None

        # Load configuration
        self.host = os.getenv("INTERNAL_API_HOST", "127.0.0.1")
        self.port = int(os.getenv("INTERNAL_API_PORT", "8082"))
        self.api_key = os.getenv("INTERNAL_API_KEY", "")
        self.env = os.getenv("ENV", "").lower()

        # Security: fail closed in production if no API key
        if not self.api_key and self.env not in {"dev", "test"}:
            raise RuntimeError(
                "INTERNAL_API_KEY must be set in production! "
                "Set ENV=dev or ENV=test for local development, "
                "or configure INTERNAL_API_KEY for production use."
            )

        if not self.api_key:
            logger.warning(
                "INTERNAL_API_KEY not set - internal API will be unsecured! "
                "This is only allowed in dev/test environments."
            )

        # Set up routes
        self.app.router.add_get("/health", self.health)
        self.app.router.add_get("/health/report", self.health_report)
        self.app.router.add_get("/errors/last", self.errors_last)
        self.app.router.add_get("/logs/export", self.logs_export)
        self.app.router.add_get("/voice/members/{channel_id}", self.get_voice_members)
        self.app.router.add_get("/guilds", self.get_guilds)
        self.app.router.add_get("/guilds/{guild_id}/roles", self.get_guild_roles)
        self.app.router.add_get("/guilds/{guild_id}/channels", self.get_guild_channels)
        self.app.router.add_get("/guilds/{guild_id}/stats", self.get_guild_stats)
        self.app.router.add_get("/guilds/{guild_id}/members", self.get_guild_members)
        self.app.router.add_get(
            "/guilds/{guild_id}/members/{user_id}", self.get_guild_member
        )
        self.app.router.add_post(
            "/guilds/{guild_id}/members/{user_id}/recheck", self.recheck_user
        )
        self.app.router.add_post(
            "/guilds/{guild_id}/config/refresh", self.refresh_guild_config
        )
        self.app.router.add_post(
            "/guilds/{guild_id}/verification/resend", self.resend_verification_message
        )
        self.app.router.add_post(
            "/guilds/{guild_id}/bulk-recheck/summary", self.post_bulk_recheck_summary
        )
        self.app.router.add_post("/guilds/{guild_id}/leave", self.leave_guild)

        logger.info(f"Internal API configured on {self.host}:{self.port}")

    async def start(self):
        """Start the internal API server."""
        try:
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            self.site = web.TCPSite(self.runner, self.host, self.port)
            await self.site.start()
            logger.info(
                f"Internal API server started on http://{self.host}:{self.port}"
            )
        except Exception as e:
            logger.exception("Failed to start internal API server", exc_info=e)
            raise

    async def stop(self):
        """Stop the internal API server."""
        try:
            if self.site:
                await self.site.stop()
            if self.runner:
                await self.runner.cleanup()
            logger.info("Internal API server stopped")
        except Exception as e:
            logger.exception("Error stopping internal API server", exc_info=e)

    def _check_auth(self, request: web.Request) -> bool:
        """Check if request has valid API key."""
        if not self.api_key:
            # No API key configured - allow all (not recommended for production)
            return True

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            return token == self.api_key

        return False

    async def health(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({"status": "ok"})

    async def health_report(self, request: web.Request) -> web.Response:
        """
        Comprehensive health report endpoint (admin only).

        Returns detailed health information including:
        - Bot status and uptime
        - Database connectivity
        - Discord gateway latency
        - System metrics (CPU, RAM)

        Path: GET /health/report
        Headers: Authorization: Bearer <api_key>
        """
        # Check authentication
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        try:
            # Get bot instance from services
            bot = self.services.bot
            if not bot:
                logger.error("Bot instance not available")
                return web.json_response({"error": "Bot not initialized"}, status=503)

            # Run health checks
            health_service = self.services.health
            health_data = await health_service.run_health_checks(
                bot, self.services.get_all_services()
            )

            # Transform to compact format for dashboard
            uptime_seconds = int(health_data["system"]["uptime_seconds"])

            report = {
                "status": health_data["overall_status"],
                "uptime_seconds": uptime_seconds,
                "db_ok": health_data["database"]["connected"],
                "discord_latency_ms": health_data["discord"].get("latency_ms"),
                "system": {
                    "cpu_percent": round(health_data["system"]["cpu_percent"], 1),
                    "memory_percent": round(health_data["system"]["memory_percent"], 1),
                },
            }

            return web.json_response(report)

        except Exception as e:
            logger.exception("Error generating health report", exc_info=e)
            return web.json_response({"error": "Internal server error"}, status=500)

    async def errors_last(self, request: web.Request) -> web.Response:
        """
        Get the most recent error log entries (admin only).

        Reads from structured error logs in logs/errors/ directory.

        Query params:
        - limit: Number of errors to return (default 1, max 100)

        Path: GET /errors/last?limit=1
        Headers: Authorization: Bearer <api_key>
        """
        # Check authentication
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        try:
            import json
            from pathlib import Path

            # Parse limit
            limit = min(int(request.query.get("limit", "1")), 100)

            # Find most recent error log file
            errors_dir = Path(__file__).parent.parent / "logs" / "errors"

            if not errors_dir.exists():
                return web.json_response({"errors": []})

            # Get all .jsonl files sorted by modification time (newest first)
            error_files = sorted(
                errors_dir.glob("errors_*.jsonl"),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )

            errors = []

            # Read from most recent files until we have enough errors
            for error_file in error_files:
                if len(errors) >= limit:
                    break

                try:
                    # Read lines in reverse order to get most recent first
                    with open(error_file) as f:
                        lines = f.readlines()

                    for line in reversed(lines):
                        if len(errors) >= limit:
                            break

                        try:
                            error_entry = json.loads(line.strip())
                            errors.append(error_entry)
                        except json.JSONDecodeError:
                            continue

                except Exception as e:
                    logger.warning(f"Could not read error file {error_file}: {e}")
                    continue

            return web.json_response({"errors": errors})

        except Exception as e:
            logger.exception("Error reading error logs", exc_info=e)
            return web.json_response({"error": "Internal server error"}, status=500)

    async def refresh_guild_config(self, request: web.Request) -> web.Response:
        """Invalidate guild configuration caches and refresh role mappings."""
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        try:
            guild_id = int(request.match_info.get("guild_id", "0"))
        except (TypeError, ValueError):
            return web.json_response({"error": "Invalid guild id"}, status=400)

        source = None
        try:
            payload = await request.json()
            if isinstance(payload, dict):
                source = payload.get("source")
        except Exception:
            pass

        cache_refreshed = False
        roles_refreshed = False

        try:
            config_service = getattr(self.services, "config", None)
            if config_service:
                await config_service.maybe_refresh_guild(guild_id, force=True)
                cache_refreshed = True

            if self.bot and hasattr(self.bot, "refresh_guild_roles"):
                await self.bot.refresh_guild_roles(guild_id, source or "config_refresh")  # type: ignore[attr-defined]
                roles_refreshed = True

            return web.json_response(
                {
                    "status": "ok",
                    "cache_refreshed": cache_refreshed,
                    "roles_refreshed": roles_refreshed,
                }
            )
        except Exception as exc:  # pragma: no cover - runtime safeguard
            logger.exception(
                "Failed to refresh guild %s configuration", guild_id, exc_info=exc
            )
            return web.json_response({"error": "Internal server error"}, status=500)

    async def resend_verification_message(self, request: web.Request) -> web.Response:
        """Send the verification message for a specific guild after channel updates."""
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        if not self.bot:
            return web.json_response({"error": "Bot unavailable"}, status=503)

        try:
            guild_id = int(request.match_info.get("guild_id", "0"))
        except (TypeError, ValueError):
            return web.json_response({"error": "Invalid guild id"}, status=400)

        guild = self.bot.get_guild(guild_id) if self.bot else None
        if guild is None:
            return web.json_response({"error": "Guild not found"}, status=404)

        try:
            cog = self.bot.get_cog("VerificationCog")
            if not cog or not hasattr(cog, "send_verification_message"):
                return web.json_response({"error": "Verification cog unavailable"}, status=503)

            # Reuse existing send_verification_message with a single-guild list
            await cog.send_verification_message([guild])  # type: ignore[misc]
            return web.json_response({"success": True})
        except Exception as exc:  # pragma: no cover - runtime safeguard
            logger.exception(
                "Failed to resend verification message for guild %s", guild_id, exc_info=exc
            )
            return web.json_response({"error": "Internal server error"}, status=500)

    async def logs_export(self, request: web.Request) -> web.Response:
        """
        Export bot logs (admin only).

        Returns the tail of the main bot log file as a downloadable attachment.

        Query params:
        - max_bytes: Maximum bytes to read from end of file (default 1MB)

        Path: GET /logs/export?max_bytes=1048576
        Headers: Authorization: Bearer <api_key>
        """
        # Check authentication
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        try:
            from pathlib import Path

            # Parse max_bytes with safe default
            max_bytes = min(
                int(request.query.get("max_bytes", "1048576")), 5 * 1024 * 1024
            )  # Cap at 5MB

            # Get current log file
            log_file = Path(__file__).parent.parent / "logs" / "bot.log"

            if not log_file.exists():
                return web.json_response({"error": "Log file not found"}, status=404)

            # Read tail of file efficiently
            file_size = log_file.stat().st_size

            if file_size <= max_bytes:
                # File is smaller than limit, read entire file
                with open(log_file, "rb") as f:
                    content = f.read()
            else:
                # Read last N bytes
                with open(log_file, "rb") as f:
                    f.seek(-max_bytes, 2)  # Seek to N bytes before end
                    content = f.read()

                    # Try to start at a newline to avoid partial line
                    first_newline = content.find(b"\n")
                    if first_newline != -1 and first_newline < 1000:
                        content = content[first_newline + 1 :]

            # Return as downloadable file
            return web.Response(
                body=content,
                headers={
                    "Content-Type": "text/plain",
                    "Content-Disposition": 'attachment; filename="bot.log.tail.txt"',
                },
            )

        except Exception as e:
            logger.exception("Error exporting logs", exc_info=e)
            return web.json_response({"error": "Internal server error"}, status=500)

    async def get_voice_members(self, request: web.Request) -> web.Response:
        """
        Get list of user IDs currently in a voice channel.

        This data comes from the Gateway cache (no Discord API overhead).

        Path: GET /voice/members/{channel_id}
        Headers: Authorization: Bearer <api_key>

        Returns: {"channel_id": int, "member_ids": [int, ...]}
        """
        # Check authentication
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        channel_id: int | None = None
        try:
            channel_id = int(request.match_info["channel_id"])

            # Get members from voice service cache
            member_ids = self.services.voice.get_voice_channel_members(channel_id)

            return web.json_response(
                {"channel_id": channel_id, "member_ids": member_ids}
            )

        except ValueError:
            return web.json_response(
                {"error": "Invalid channel_id - must be integer"}, status=400
            )
        except Exception as e:
            logger.exception(
                f"Error getting voice members for channel {channel_id}", exc_info=e
            )
            return web.json_response({"error": "Internal server error"}, status=500)

    async def get_guilds(self, request: web.Request) -> web.Response:
        """Return guilds where the bot is currently installed."""
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        if not self.bot:
            return web.json_response({"error": "Bot unavailable"}, status=503)

        guilds = []
        for guild in self.bot.guilds:
            try:
                icon_url = str(guild.icon.url) if guild.icon else None
            except Exception:
                icon_url = None

            guilds.append(
                {
                    "guild_id": guild.id,
                    "guild_name": guild.name,
                    "icon_url": icon_url,
                }
            )

        return web.json_response({"guilds": guilds})

    async def leave_guild(self, request: web.Request) -> web.Response:
        """
        Make the bot leave a guild (bot owner only).

        This is a privileged operation that should only be called by the bot owner.
        The web backend is responsible for validating bot owner permissions.

        Path: POST /guilds/{guild_id}/leave
        Headers: Authorization: Bearer <api_key>
        """
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        if not self.bot:
            return web.json_response({"error": "Bot unavailable"}, status=503)

        try:
            guild_id = int(request.match_info["guild_id"])
        except (KeyError, ValueError):
            return web.json_response({"error": "Invalid guild ID"}, status=400)

        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return web.json_response({"error": "Guild not found"}, status=404)

        guild_name = guild.name
        try:
            await guild.leave()
            logger.info(f"Bot left guild {guild_id} ({guild_name})")
            return web.json_response({
                "success": True,
                "guild_id": guild_id,
                "guild_name": guild_name,
            })
        except Exception as e:
            logger.exception(f"Failed to leave guild {guild_id}", exc_info=e)
            return web.json_response({"error": "Failed to leave guild"}, status=500)

    async def get_guild_roles(self, request: web.Request) -> web.Response:
        """Return Discord roles for a guild."""
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        if not self.bot:
            return web.json_response({"error": "Bot unavailable"}, status=503)

        try:
            guild_id = int(request.match_info["guild_id"])
        except (KeyError, ValueError):
            return web.json_response({"error": "Invalid guild ID"}, status=400)

        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return web.json_response({"error": "Guild not found"}, status=404)

        roles_payload = []
        for role in sorted(guild.roles, key=lambda r: r.position, reverse=True):
            if role.is_default():
                continue  # Skip @everyone
            roles_payload.append(
                {
                    "id": role.id,
                    "name": role.name,
                    "color": role.color.value if role.color else None,
                }
            )

        return web.json_response({"roles": roles_payload})

    async def get_guild_channels(self, request: web.Request) -> web.Response:
        """Return all channels (text, voice, stage) for a guild."""
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        if not self.bot:
            return web.json_response({"error": "Bot unavailable"}, status=503)

        try:
            guild_id = int(request.match_info["guild_id"])
        except (KeyError, ValueError):
            return web.json_response({"error": "Invalid guild ID"}, status=400)

        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return web.json_response({"error": "Guild not found"}, status=404)

        channels_payload = []
        # Include all channel types: text (0), voice (2), stage (13), category (4), forum (15), etc.
        for channel in guild.channels:
            # Get category name if channel is in a category
            category_name = (
                channel.category.name
                if hasattr(channel, "category") and channel.category
                else "Uncategorized"
            )

            # Get channel type
            channel_type = channel.type.value if hasattr(channel, "type") else None

            channels_payload.append(
                {
                    "id": str(channel.id),  # Send as string to preserve precision
                    "name": channel.name,
                    "type": channel_type,  # 0=text, 2=voice, 4=category, 13=stage, 15=forum
                    "category": category_name,
                    "position": channel.position if hasattr(channel, "position") else 0,
                }
            )

        # Sort by position
        channels_payload.sort(key=lambda c: c["position"])

        return web.json_response({"channels": channels_payload})

    async def get_guild_stats(self, request: web.Request) -> web.Response:
        """
        Return basic statistics for a guild (member count, etc).

        This provides data needed to calculate true unverified counts.

        Path: GET /guilds/{guild_id}/stats
        Headers: Authorization: Bearer <api_key>

        Returns: {
            "guild_id": int,
            "member_count": int,  # Total guild members (from Gateway cache)
            "approximate_member_count": int | None  # Approximate count if available
        }
        """
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        if not self.bot:
            return web.json_response({"error": "Bot unavailable"}, status=503)

        try:
            guild_id = int(request.match_info["guild_id"])
        except (KeyError, ValueError):
            return web.json_response({"error": "Invalid guild ID"}, status=400)

        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return web.json_response({"error": "Guild not found"}, status=404)

        # Get member count from cached guild object
        # Note: This is accurate if bot has members intent enabled
        member_count = guild.member_count or 0

        # Also include approximate_member_count if available (from guild object)
        approximate_member_count = getattr(guild, "approximate_member_count", None)

        return web.json_response(
            {
                "guild_id": guild.id,
                "member_count": member_count,
                "approximate_member_count": approximate_member_count,
            }
        )

    async def get_guild_members(self, request: web.Request) -> web.Response:
        """
        Get paginated list of guild members with enriched Discord data.

        Query params:
        - page: Page number (default 1)
        - page_size: Items per page (default 100, max 1000)

        Path: GET /guilds/{guild_id}/members?page=1&page_size=100
        Headers: Authorization: Bearer <api_key>

        Returns: {
            "members": [{
                "user_id": int,
                "username": str,
                "discriminator": str,
                "global_name": str | None,
                "avatar_url": str | None,
                "joined_at": str (ISO),
                "created_at": str (ISO),
                "roles": [{"id": int, "name": str, "color": int}]
            }],
            "page": int,
            "page_size": int,
            "total": int
        }
        """
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        if not self.bot:
            return web.json_response({"error": "Bot unavailable"}, status=503)

        try:
            guild_id = int(request.match_info["guild_id"])
        except (KeyError, ValueError):
            return web.json_response({"error": "Invalid guild ID"}, status=400)

        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return web.json_response({"error": "Guild not found"}, status=404)

        # Parse pagination params
        try:
            page = int(request.query.get("page", "1"))
            page_size = min(int(request.query.get("page_size", "100")), 1000)
            page = max(1, page)
            page_size = max(1, page_size)
        except ValueError:
            return web.json_response(
                {"error": "Invalid pagination parameters"}, status=400
            )

        # Get all members (from cache)
        all_members = list(guild.members)
        total = len(all_members)

        # Calculate pagination
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_members = all_members[start_idx:end_idx]

        # Build response
        members_data = []
        for member in page_members:
            try:
                avatar_url = str(member.avatar.url) if member.avatar else None
            except Exception:
                avatar_url = None

            # Get roles (excluding @everyone)
            roles_data = []
            for role in member.roles:
                if role.is_default():
                    continue
                roles_data.append(
                    {
                        "id": role.id,
                        "name": role.name,
                        "color": role.color.value if role.color else None,
                    }
                )

            members_data.append(
                {
                    "user_id": member.id,
                    "username": member.name,
                    "discriminator": member.discriminator,
                    "global_name": member.global_name,
                    "avatar_url": avatar_url,
                    "joined_at": member.joined_at.isoformat()
                    if member.joined_at
                    else None,
                    "created_at": member.created_at.isoformat()
                    if member.created_at
                    else None,
                    "roles": roles_data,
                }
            )

        return web.json_response(
            {
                "members": members_data,
                "page": page,
                "page_size": page_size,
                "total": total,
            }
        )

    async def get_guild_member(self, request: web.Request) -> web.Response:
        """
        Get single guild member with enriched Discord data.

        Path: GET /guilds/{guild_id}/members/{user_id}
        Headers: Authorization: Bearer <api_key>

        Returns: {
            "user_id": int,
            "username": str,
            "discriminator": str,
            "global_name": str | None,
            "avatar_url": str | None,
            "joined_at": str (ISO),
            "created_at": str (ISO),
            "roles": [{"id": int, "name": str, "color": int}]
        }
        """
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        if not self.bot:
            return web.json_response({"error": "Bot unavailable"}, status=503)

        try:
            guild_id = int(request.match_info["guild_id"])
            user_id = int(request.match_info["user_id"])
        except (KeyError, ValueError):
            return web.json_response({"error": "Invalid guild or user ID"}, status=400)

        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return web.json_response({"error": "Guild not found"}, status=404)

        # Try to get member from cache first
        member = guild.get_member(user_id)
        source = "gateway_cache"
        if member is None:
            # Try to fetch from API
            try:
                member = await guild.fetch_member(user_id)
                source = "api_refresh"
            except Exception as e:
                logger.warning(
                    f"Could not fetch member {user_id} from guild {guild_id}: {e}"
                )
                return web.json_response({"error": "Member not found"}, status=404)

        try:
            avatar_url = str(member.avatar.url) if member.avatar else None
        except Exception:
            avatar_url = None

        # Get roles (excluding @everyone)
        roles_data = []
        role_ids = []
        for role in member.roles:
            if role.is_default():
                continue
            roles_data.append(
                {
                    "id": role.id,
                    "name": role.name,
                    "color": role.color.value if role.color else None,
                }
            )
            role_ids.append(role.id)

        return web.json_response(
            {
                "guild_id": guild.id,
                "user_id": member.id,
                "username": member.name,
                "discriminator": member.discriminator,
                "global_name": member.global_name,
                "avatar_url": avatar_url,
                "joined_at": member.joined_at.isoformat() if member.joined_at else None,
                "created_at": member.created_at.isoformat()
                if member.created_at
                else None,
                "roles": roles_data,
                "role_ids": role_ids,
                "last_synced_at": datetime.now(UTC).isoformat(),
                "source": source,
            }
        )

    async def recheck_user(self, request: web.Request) -> web.Response:
        """
        Trigger reverification check for a specific user.

        Path: POST /guilds/{guild_id}/members/{user_id}/recheck
        Headers: Authorization: Bearer <api_key>
        Body (optional): {"admin_user_id": "123456789"}

        Returns: {
            "success": bool,
            "message": str,
            "status": str,
            "diff": dict,
            "rate_limited": bool,
            "wait_until": int,
            "remediated": bool
        }
        """
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        if not self.bot:
            return web.json_response({"error": "Bot unavailable"}, status=503)

        try:
            guild_id = int(request.match_info["guild_id"])
            user_id = int(request.match_info["user_id"])
        except (KeyError, ValueError):
            return web.json_response({"error": "Invalid guild or user ID"}, status=400)

        # Parse optional admin_user_id from request body
        admin_user_id = None
        try:
            body = await request.json()
            admin_user_id = body.get("admin_user_id")
        except Exception:
            pass  # No body or invalid JSON, proceed without admin_user_id

        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return web.json_response({"error": "Guild not found"}, status=404)

        # Get member
        member = guild.get_member(user_id)
        if member is None:
            try:
                member = await guild.fetch_member(user_id)
            except Exception as e:
                logger.warning(f"Could not fetch member {user_id}: {e}")
                return web.json_response({"error": "Member not found"}, status=404)

        # Get the member's RSI handle from verification database
        try:
            row = await BaseRepository.fetch_one(
                "SELECT rsi_handle FROM verification WHERE user_id = ?", (user_id,)
            )

            if not row or not row[0]:
                return web.json_response(
                    {
                        "error": "User has no RSI handle on record. They need to verify first."
                    },
                    status=400,
                )

            rsi_handle = row[0]

        except Exception as e:
            logger.exception(f"Error fetching RSI handle for user {user_id}: {e}")
            return web.json_response({"error": f"Database error: {e!s}"}, status=500)

        # Use unified recheck service
        if not self.bot:
            return web.json_response(
                {"error": "Bot instance not available"}, status=503
            )

        try:
            from helpers.recheck_service import perform_recheck

            result = await perform_recheck(
                member=member,
                rsi_handle=rsi_handle,
                bot=self.bot,
                initiator_kind=InitiatorKind.ADMIN,
                initiator_source=InitiatorSource.WEB,
                admin_user_id=admin_user_id,
                enforce_rate_limit=False,  # Admin actions bypass rate limits
                log_leadership=True,  # Always log leadership changes
                log_audit=True,  # Always audit admin actions
            )

            # Handle rate limiting (shouldn't happen with enforce_rate_limit=False)
            if result["rate_limited"]:
                return web.json_response(
                    {"error": "Rate limited", "wait_until": result["wait_until"]},
                    status=429,
                )

            # Handle remediation (404)
            if result["remediated"]:
                return web.json_response(
                    {"error": result["error"], "remediated": True}, status=404
                )

            # Handle other errors
            if not result["success"]:
                return web.json_response({"error": result["error"]}, status=500)

            # Success!
            return web.json_response(
                {
                    "success": True,
                    "message": "User rechecked successfully",
                    "status": result["status"],
                    "diff": result["diff"],
                    "roles_updated": True,
                }
            )

        except Exception as e:
            logger.exception(
                f"Error rechecking user {user_id} in guild {guild_id}: {e}"
            )
            return web.json_response({"error": f"Recheck failed: {e!s}"}, status=500)

    async def post_bulk_recheck_summary(self, request: web.Request) -> web.Response:
        """
        Post bulk recheck summary to leadership channel.

        Path: POST /guilds/{guild_id}/bulk-recheck/summary
        Headers: Authorization: Bearer <api_key>
        Body: {
            "admin_user_id": int,
            "scope_label": str,
            "status_rows": list[dict],  # List of StatusRow data
            "csv_bytes": str (base64),
            "csv_filename": str
        }

        Returns: {
            "success": bool,
            "channel_name": str
        }
        """
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        if not self.bot:
            return web.json_response({"error": "Bot unavailable"}, status=503)

        try:
            guild_id = int(request.match_info["guild_id"])
        except (KeyError, ValueError):
            return web.json_response({"error": "Invalid guild ID"}, status=400)

        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return web.json_response({"error": "Guild not found"}, status=404)

        # Parse request body
        try:
            body = await request.json()
            admin_user_id = body["admin_user_id"]
            scope_label = body.get("scope_label", "specific users")
            status_rows_data = body["status_rows"]
            csv_base64 = body["csv_bytes"]
            csv_filename = body["csv_filename"]
        except (KeyError, ValueError) as e:
            return web.json_response(
                {"error": f"Missing or invalid request fields: {e}"}, status=400
            )

        # Get the admin member who initiated the recheck
        invoker = guild.get_member(admin_user_id)
        if invoker is None:
            try:
                invoker = await guild.fetch_member(admin_user_id)
            except Exception:
                return web.json_response(
                    {"error": "Admin user not found in guild"}, status=404
                )

        # Decode CSV from base64
        try:
            csv_bytes = base64.b64decode(csv_base64)
        except Exception as e:
            return web.json_response(
                {"error": f"Invalid base64 CSV data: {e}"}, status=400
            )

        # Reconstruct StatusRow objects from data using class method
        try:
            status_rows = [StatusRow.from_dict(row) for row in status_rows_data]
        except Exception as e:
            return web.json_response(
                {"error": f"Invalid status rows data: {e}"}, status=400
            )

        # Build embed using the same helper as Discord bulk verification
        try:
            # Get member objects for embed generation
            members = [
                member
                for row in status_rows
                if (member := guild.get_member(row.user_id))
            ]

            embed = build_summary_embed(
                invoker=invoker,
                members=members,
                rows=status_rows,
                truncated_count=0,
                scope_label=scope_label,
                scope_channel=None,  # Not applicable for web bulk recheck
            )
        except Exception as e:
            logger.exception(f"Error building summary embed: {e}")
            return web.json_response(
                {"error": f"Failed to build embed: {e!s}"}, status=500
            )

        # Send to leadership channel using existing helper
        try:
            channel_name = await send_admin_bulk_check_summary(
                cast("MyBot", self.bot),
                guild=guild,
                invoker=invoker,
                scope_label=scope_label,
                scope_channel=None,
                embed=embed,
                csv_bytes=csv_bytes,
                csv_filename=csv_filename,
            )

            return web.json_response(
                {"success": True, "channel_name": channel_name}
            )

        except Exception as e:
            logger.exception(
                f"Error posting bulk recheck summary to leadership channel: {e}"
            )
            return web.json_response(
                {"error": f"Failed to post to leadership channel: {e!s}"}, status=500
            )
