"""Shared helpers for ticket-related API routes.

Centralises common validation logic used by both the ticket and
ticket-form router modules, keeping things DRY.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException

if TYPE_CHECKING:
    from backend.db.repository.tickets import TicketRepository


async def require_guild_category(
    repo: TicketRepository, category_id: int, guild_id: int
) -> dict:
    """Verify a category exists and belongs to the given guild.

    Raises:
        HTTPException(404): When the category does not exist or belongs to
            a different guild.

    Returns:
        The category dict from ``TicketRepository.get_category()``.
    """
    cat = await repo.get_category(category_id)
    if cat is None or cat["guild_id"] != guild_id:
        raise HTTPException(status_code=404, detail="Category not found")
    return cat
