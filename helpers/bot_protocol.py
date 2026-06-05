"""
Bot protocol for type-checking helper views without creating import cycles.

Views that need access to MyBot-specific attributes (e.g., ``bot.services``)
should annotate their ``bot`` parameter as ``BotProtocol`` instead of
importing ``MyBot`` from ``bot``, which creates a stub cycle in pyright.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import discord

    from connectors.registry import ConnectorRegistry
    from services.service_container import ServiceContainer


class BotProtocol(Protocol):
    """Structural type for the bot instance used in helper views.

    Any class that exposes a ``services`` attribute of type
    :class:`~services.service_container.ServiceContainer` satisfies this
    protocol.  ``MyBot`` satisfies it automatically without any explicit
    declaration.
    """

    services: ServiceContainer
    connectors: ConnectorRegistry | None

    def get_channel(
        self,
        id: int,  # noqa: A002
        /,
    ) -> (
        discord.abc.GuildChannel | discord.Thread | discord.abc.PrivateChannel | None
    ): ...


def require_connectors(bot: BotProtocol) -> ConnectorRegistry:
    """Return initialized connectors or raise a clear runtime error."""
    connectors = bot.connectors
    if connectors is None:
        raise RuntimeError("Bot connectors are not initialized")
    return connectors
