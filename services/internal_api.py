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
        self.app = web.Application()
        self.runner = None
        self.site = None
        
        # Load configuration
        self.host = os.getenv("INTERNAL_API_HOST", "127.0.0.1")
        self.port = int(os.getenv("INTERNAL_API_PORT", "8082"))
        self.api_key = os.getenv("INTERNAL_API_KEY", "")
        
        if not self.api_key:
            logger.warning(
                "INTERNAL_API_KEY not set - internal API will be unsecured! "
                "Set this in production."
            )
        
        # Set up routes
        self.app.router.add_get("/health", self.health)
        self.app.router.add_get("/voice/members/{channel_id}", self.get_voice_members)
        
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
