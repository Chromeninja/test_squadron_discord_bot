"""Typed connector registry attached to the bot instance."""
from __future__ import annotations

from dataclasses import dataclass

from .config import ConfigConnector
from .events import EventsConnector
from .metrics import MetricsConnector
from .tickets import TicketsConnector
from .verification import VerificationConnector
from .voice import VoiceConnector


@dataclass
class ConnectorRegistry:
    """Typed registry of all domain connectors.

    Attached to ``bot.connectors`` when ``BACKEND_URL`` and ``BOT_API_KEY``
    are present in the environment.  Access individual connectors via
    ``bot.connectors.events``, ``bot.connectors.voice``, etc.
    """

    events: EventsConnector
    voice: VoiceConnector
    tickets: TicketsConnector
    verification: VerificationConnector
    config: ConfigConnector
    metrics: MetricsConnector
