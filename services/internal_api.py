"""
Internal API server for bot-to-web communication.

Provides HTTP endpoints for the web dashboard to query bot state
without hitting Discord API rate limits.
"""

import os
from typing import TYPE_CHECKING

from aiohttp import web

from utils.logging import get_logger

if TYPE_CHECKING:
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
        self.app.router.add_get("/guilds/{guild_id}/members/{user_id}", self.get_guild_member)

        logger.info(f"Internal API configured on {self.host}:{self.port}")

    async def start(self):
        """Start the internal API server."""
        try:
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            self.site = web.TCPSite(self.runner, self.host, self.port)
            await self.site.start()
            logger.info(f"Internal API server started on http://{self.host}:{self.port}")
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
            return web.json_response(
                {"error": "Unauthorized"},
                status=401
            )

        try:
            # Get bot instance from services
            bot = self.services.bot

            # Run health checks
            health_service = self.services.health
            health_data = await health_service.run_health_checks(
                bot,
                self.services.get_all_services()
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
                }
            }

            return web.json_response(report)

        except Exception as e:
            logger.exception("Error generating health report", exc_info=e)
            return web.json_response(
                {"error": "Internal server error"},
                status=500
            )

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
            return web.json_response(
                {"error": "Unauthorized"},
                status=401
            )

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
                reverse=True
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
            return web.json_response(
                {"error": "Internal server error"},
                status=500
            )

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
            return web.json_response(
                {"error": "Unauthorized"},
                status=401
            )

        try:
            from pathlib import Path

            # Parse max_bytes with safe default
            max_bytes = min(int(request.query.get("max_bytes", "1048576")), 5 * 1024 * 1024)  # Cap at 5MB

            # Get current log file
            log_file = Path(__file__).parent.parent / "logs" / "bot.log"

            if not log_file.exists():
                return web.json_response(
                    {"error": "Log file not found"},
                    status=404
                )

            # Read tail of file efficiently
            file_size = log_file.stat().st_size

            if file_size <= max_bytes:
                # File is smaller than limit, read entire file
                with open(log_file, 'rb') as f:
                    content = f.read()
            else:
                # Read last N bytes
                with open(log_file, 'rb') as f:
                    f.seek(-max_bytes, 2)  # Seek to N bytes before end
                    content = f.read()

                    # Try to start at a newline to avoid partial line
                    first_newline = content.find(b'\n')
                    if first_newline != -1 and first_newline < 1000:
                        content = content[first_newline + 1:]

            # Return as downloadable file
            return web.Response(
                body=content,
                headers={
                    'Content-Type': 'text/plain',
                    'Content-Disposition': 'attachment; filename="bot.log.tail.txt"'
                }
            )

        except Exception as e:
            logger.exception("Error exporting logs", exc_info=e)
            return web.json_response(
                {"error": "Internal server error"},
                status=500
            )

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
            return web.json_response(
                {"error": "Unauthorized"},
                status=401
            )

        try:
            channel_id = int(request.match_info["channel_id"])

            # Get members from voice service cache
            member_ids = self.services.voice.get_voice_channel_members(channel_id)

            return web.json_response({
                "channel_id": channel_id,
                "member_ids": member_ids
            })

        except ValueError:
            return web.json_response(
                {"error": "Invalid channel_id - must be integer"},
                status=400
            )
        except Exception as e:
            logger.exception(f"Error getting voice members for channel {channel_id}", exc_info=e)
            return web.json_response(
                {"error": "Internal server error"},
                status=500
            )

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
        """Return text channels for a guild."""
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
        for channel in guild.text_channels:
            # Get category name if channel is in a category
            category_name = channel.category.name if channel.category else "Uncategorized"
            
            channels_payload.append(
                {
                    "id": str(channel.id),  # Send as string to preserve precision
                    "name": channel.name,
                    "category": category_name,
                    "position": channel.position,
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
        approximate_member_count = getattr(guild, 'approximate_member_count', None)

        return web.json_response({
            "guild_id": guild.id,
            "member_count": member_count,
            "approximate_member_count": approximate_member_count
        })

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
            return web.json_response({"error": "Invalid pagination parameters"}, status=400)

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
                roles_data.append({
                    "id": role.id,
                    "name": role.name,
                    "color": role.color.value if role.color else None
                })

            members_data.append({
                "user_id": member.id,
                "username": member.name,
                "discriminator": member.discriminator,
                "global_name": member.global_name,
                "avatar_url": avatar_url,
                "joined_at": member.joined_at.isoformat() if member.joined_at else None,
                "created_at": member.created_at.isoformat() if member.created_at else None,
                "roles": roles_data
            })

        return web.json_response({
            "members": members_data,
            "page": page,
            "page_size": page_size,
            "total": total
        })

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
        if member is None:
            # Try to fetch from API
            try:
                member = await guild.fetch_member(user_id)
            except Exception as e:
                logger.warning(f"Could not fetch member {user_id} from guild {guild_id}: {e}")
                return web.json_response({"error": "Member not found"}, status=404)

        try:
            avatar_url = str(member.avatar.url) if member.avatar else None
        except Exception:
            avatar_url = None

        # Get roles (excluding @everyone)
        roles_data = []
        for role in member.roles:
            if role.is_default():
                continue
            roles_data.append({
                "id": role.id,
                "name": role.name,
                "color": role.color.value if role.color else None
            })

        return web.json_response({
            "user_id": member.id,
            "username": member.name,
            "discriminator": member.discriminator,
            "global_name": member.global_name,
            "avatar_url": avatar_url,
            "joined_at": member.joined_at.isoformat() if member.joined_at else None,
            "created_at": member.created_at.isoformat() if member.created_at else None,
            "roles": roles_data
        })
