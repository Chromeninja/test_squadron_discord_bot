"""
Bot protocol for type-checking helper views without creating import cycles.

Views that need access to MyBot-specific attributes (e.g., ``bot.services``)
should annotate their ``bot`` parameter as ``BotProtocol`` instead of
importing ``MyBot`` from ``bot``, which creates a stub cycle in pyright.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import discord

if TYPE_CHECKING:
    from services.service_container import ServiceContainer


class BotProtocol(Protocol):
    """Structural type for the bot instance used in helper views.

    Any class that exposes a ``services`` attribute of type
    :class:`~services.service_container.ServiceContainer` satisfies this
    protocol.  ``MyBot`` satisfies it automatically without any explicit
    declaration.
    """

    services: "ServiceContainer"

    def get_channel(
        self, id: int, /
    ) -> (
        discord.abc.GuildChannel
        | discord.Thread
        | discord.abc.PrivateChannel
        | None
    ): ...
