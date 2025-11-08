"""
User search endpoints for verification records.
"""

from fastapi import APIRouter, Depends, Query

from core.dependencies import get_db, require_admin_or_moderator
from core.schemas import UserProfile, UserSearchResponse, VerificationRecord

router = APIRouter()


@router.get("/search", response_model=UserSearchResponse)
async def search_users(
    query: str = Query("", description="Search by user_id, rsi_handle, or community_moniker"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_admin_or_moderator),
):
    """
    Search verification records.

    Searches by:
    - user_id (exact match)
    - rsi_handle (case-insensitive partial match)
    - community_moniker (case-insensitive partial match)

    Requires: Admin or moderator role

    Args:
        query: Search term
        page: Page number (1-indexed)
        page_size: Results per page (max 100)

    Returns:
        UserSearchResponse with paginated results
    """
    offset = (page - 1) * page_size

    if not query:
        # Return all users (paginated)
        count_cursor = await db.execute("SELECT COUNT(*) FROM verification")
        count_row = await count_cursor.fetchone()
        total = count_row[0] if count_row else 0

        cursor = await db.execute(
            """
            SELECT 
                user_id, rsi_handle, membership_status, 
                community_moniker, last_updated, needs_reverify
            FROM verification
            ORDER BY last_updated DESC
            LIMIT ? OFFSET ?
            """,
            (page_size, offset),
        )
        rows = await cursor.fetchall()
    else:
        # Try exact user_id match first
        try:
            user_id_int = int(query)
            count_cursor = await db.execute(
                "SELECT COUNT(*) FROM verification WHERE user_id = ?",
                (user_id_int,),
            )
            count_row = await count_cursor.fetchone()
            total = count_row[0] if count_row else 0

            cursor = await db.execute(
                """
                SELECT 
                    user_id, rsi_handle, membership_status,
                    community_moniker, last_updated, needs_reverify
                FROM verification
                WHERE user_id = ?
                LIMIT ? OFFSET ?
                """,
                (user_id_int, page_size, offset),
            )
            rows = await cursor.fetchall()
        except ValueError:
            # Not a valid integer, search by handle or moniker
            search_pattern = f"%{query}%"

            count_cursor = await db.execute(
                """
                SELECT COUNT(*) FROM verification
                WHERE rsi_handle LIKE ? OR community_moniker LIKE ?
                """,
                (search_pattern, search_pattern),
            )
            count_row = await count_cursor.fetchone()
            total = count_row[0] if count_row else 0

            cursor = await db.execute(
                """
                SELECT 
                    user_id, rsi_handle, membership_status,
                    community_moniker, last_updated, needs_reverify
                FROM verification
                WHERE rsi_handle LIKE ? OR community_moniker LIKE ?
                ORDER BY last_updated DESC
                LIMIT ? OFFSET ?
                """,
                (search_pattern, search_pattern, page_size, offset),
            )
            rows = await cursor.fetchall()

    # Convert rows to VerificationRecord objects
    items = []
    for row in rows:
        items.append(
            VerificationRecord(
                user_id=row[0],
                rsi_handle=row[1],
                membership_status=row[2],
                community_moniker=row[3],
                last_updated=row[4],
                needs_reverify=bool(row[5]),
            )
        )

    return UserSearchResponse(
        success=True,
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )
