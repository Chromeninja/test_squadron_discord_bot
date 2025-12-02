"""
Voice channel recheck helper: rechecks all users in a voice channel, one at a time, using bulk recheck logic.
Returns per-user results, summary, and CSV export.
"""

import discord

from helpers.bulk_check import StatusRow, write_csv


async def recheck_voice_channel(
    channel: discord.VoiceChannel, bot, initiator_kind="Admin", admin_user_id=None
):
    results = []
    from services.db.database import Database

    async with Database.get_connection() as db:
        for member in channel.members:
            # Fetch RSI handle from DB
            cursor = await db.execute(
                "SELECT rsi_handle, last_updated FROM verification WHERE user_id = ?",
                (member.id,),
            )
            row_db = await cursor.fetchone()
            rsi_handle = row_db[0] if row_db else None
            last_updated = row_db[1] if row_db else None
            if not rsi_handle:
                continue
            # Call the unified recheck logic (imported from helpers.recheck_service)
            from helpers.recheck_service import perform_recheck

            recheck_result = await perform_recheck(
                member,
                rsi_handle,
                bot,
                initiator_kind=initiator_kind,
                admin_user_id=admin_user_id,
                enforce_rate_limit=False,
                log_leadership=True,
                log_audit=True,
            )
            # Build StatusRow for each member
            row = StatusRow(
                user_id=member.id,
                username=member.display_name,
                rsi_handle=rsi_handle,
                membership_status=recheck_result.get("status"),
                last_updated=last_updated,
                voice_channel=channel.name,
                rsi_status=recheck_result.get("status"),
                rsi_checked_at=None,  # Fill as needed
                rsi_error=recheck_result.get("error"),
            )
            results.append(row)
    # Write CSV
    filename, csv_content = write_csv(
        results, guild_name=channel.guild.name, invoker_name=initiator_kind
    )
    # Build summary
    summary = f"Rechecked {len(results)} users in voice channel '{channel.name}'."
    return {
        "results": results,
        "summary": summary,
        "csv_filename": filename,
        "csv_content": csv_content,
    }
