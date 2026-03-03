from typing import Any

import discord
from discord.ext import commands

from helpers.http_helper import HTTPClient
from services.internal_api import InternalAPIServer
from services.service_container import ServiceContainer

class MyBot(commands.Bot):
    """
    Extended Bot class with custom attributes for TEST Squadron bot.

    Attributes:
        config: Global configuration dictionary loaded from config.yaml
        services: Service container providing access to all bot services
        http_client: HTTP client for making external API requests
        role_cache: Cache of Discord role objects for quick access
        start_time: Monotonic timestamp when bot started
        owner_id: Discord user ID of the bot owner
        internal_api: Internal API server for web dashboard
    """

    config: dict[str, Any]
    services: ServiceContainer
    http_client: HTTPClient
    role_cache: dict[str, object]
    start_time: float
    owner_id: int | None
    internal_api: InternalAPIServer | None

    # Private attributes for internal tracking
    _missing_role_warned_guilds: set[int]
    _guild_role_expectations: dict[int, set[str]]

# Module-level attributes for type checking
PREFIX: Any
intents: discord.Intents
initial_extensions: list[str]
