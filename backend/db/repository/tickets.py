"""Backward-compatible re-export for TicketRepository.

Implementation split into tickets_core.py (CRUD) and tickets_stats.py (stats mixin).
"""

from backend.db.repository.tickets_core import TicketRepository

# Backward-compat alias — stats methods are available on TicketRepository via mixin.
TicketStatsRepository = TicketRepository

__all__ = ["TicketRepository", "TicketStatsRepository"]
