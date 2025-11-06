"""
Verification Bulk Service

Manages queued batch-processing jobs for bulk verification status checks.
This handles READ-ONLY status checks only (no RSI verification).
Coordinates with auto-recheck loop to avoid conflicts.
"""

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import discord

from utils.logging import get_logger

if TYPE_CHECKING:
    from discord.ext import commands


logger = get_logger(__name__)


@dataclass
class RsiStatusResult:
    """Result from an RSI organization status check."""
    status: str  # "main" | "affiliate" | "non_member" | "unknown"
    checked_at: int  # Unix timestamp
    error: str | None = None  # Error message if check failed


@dataclass
class BulkVerificationJob:
    """Represents a single bulk verification status check job."""
    job_id: int
    guild_id: int
    target_member_ids: list[int]

    # Manual job fields
    invoker_id: int
    interaction: discord.Interaction
    scope_label: str  # "specific users" | "voice channel" | "all active voice"
    scope_channel: str | None = None  # Channel name if applicable

    # RSI recheck option
    recheck_rsi: bool = False  # If True, verify RSI org status for each user

    # Tracking
    queued_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None

    # Results
    status_rows: list = field(default_factory=list)  # list[StatusRow] - avoid circular import
    errors: list[tuple[int, str, str]] = field(default_factory=list)  # (user_id, display_name, error)


class VerificationBulkService:
    """
    Service for managing bulk verification status check jobs.
    
    Processes jobs sequentially with batching and rate limiting.
    Signals auto-recheck to pause when manual checks are running.
    """

    def __init__(self, bot: "commands.Bot"):
        self.bot = bot
        self.queue: asyncio.Queue[BulkVerificationJob] = asyncio.Queue()
        self.lock = asyncio.Lock()  # Mutex for processing
        self.worker_task: asyncio.Task | None = None
        self.current_job: BulkVerificationJob | None = None
        self._job_counter = 0
        self._running = False

    async def start(self) -> None:
        """Start the worker task."""
        if self.worker_task is not None:
            logger.warning("VerificationBulkService worker already running")
            return

        self._running = True
        self.worker_task = asyncio.create_task(self._worker_loop())
        logger.info("VerificationBulkService worker started")

    async def shutdown(self) -> None:
        """Stop the worker task cleanly."""
        self._running = False

        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
            self.worker_task = None

        logger.info("VerificationBulkService worker stopped")

    async def enqueue_manual(
        self,
        interaction: discord.Interaction,
        members: list[discord.Member],
        scope_label: str,
        scope_channel: str | None = None,
        recheck_rsi: bool = False
    ) -> int:
        """
        Enqueue a manual admin-initiated bulk check job.
        
        Returns:
            job_id for tracking
        """
        self._job_counter += 1
        job_id = self._job_counter

        job = BulkVerificationJob(
            job_id=job_id,
            guild_id=interaction.guild_id,
            target_member_ids=[m.id for m in members],
            invoker_id=interaction.user.id,
            interaction=interaction,
            scope_label=scope_label,
            scope_channel=scope_channel,
            recheck_rsi=recheck_rsi
        )

        await self.queue.put(job)
        logger.info(f"Enqueued manual status check job {job_id} with {len(members)} targets by user {interaction.user.id} (recheck_rsi={recheck_rsi})")
        return job_id

    def is_running(self) -> bool:
        """Check if a job is currently processing."""
        return self.current_job is not None

    def queue_size(self) -> int:
        """Get current queue size."""
        return self.queue.qsize()

    async def _worker_loop(self) -> None:
        """Main worker loop that processes jobs from the queue."""
        while self._running:
            try:
                # Wait for next job with timeout to allow clean shutdown
                try:
                    job = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                except TimeoutError:
                    continue

                async with self.lock:
                    self.current_job = job
                    try:
                        await self._process_job(job)
                    except Exception as e:
                        logger.exception(f"Error processing job {job.job_id}: {e}")
                        # Notify user of failure
                        try:
                            await job.interaction.followup.send(
                                f"❌ Job failed unexpectedly: {e!s}",
                                ephemeral=True
                            )
                        except Exception:
                            pass
                    finally:
                        self.current_job = None
                        self.queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Unexpected error in worker loop: {e}")
                await asyncio.sleep(1)

    async def _process_job(self, job: BulkVerificationJob) -> None:
        """Process a single bulk verification status check job."""
        job.started_at = time.time()
        logger.info(f"Processing status check job {job.job_id} with {len(job.target_member_ids)} targets")

        # Early notification and validation
        guild = await self._notify_job_start(job)
        if not guild:
            return

        # Process all batches
        batch_size = self._get_batch_size()
        await self._process_batches(job, guild, batch_size)

        # Finalize and deliver
        job.completed_at = time.time()
        await self._deliver_results(job, guild)
        logger.info(f"Completed status check job {job.job_id}: {len(job.status_rows)} successful, {len(job.errors)} errors")

    async def _notify_job_start(self, job: BulkVerificationJob) -> discord.Guild | None:
        """Send initial notification and validate guild. Returns guild or None if invalid."""
        queue_size = self.queue_size()
        if queue_size > 0:
            await job.interaction.followup.send(
                f"⏳ Processing started (queued behind {queue_size} other job(s)). Checking {len(job.target_member_ids)} users...",
                ephemeral=True
            )

        guild = self.bot.get_guild(job.guild_id)
        if not guild:
            logger.error(f"Guild {job.guild_id} not found for job {job.job_id}")
            return None
        
        return guild

    def _get_batch_size(self) -> int:
        """Get configured batch size for processing."""
        return self.bot.config.get("auto_recheck", {}).get("batch", {}).get("max_users_per_run", 50)

    async def _process_batches(self, job: BulkVerificationJob, guild: discord.Guild, batch_size: int) -> None:
        """Process all target members in batches."""
        total_targets = len(job.target_member_ids)
        processed = 0

        for i in range(0, total_targets, batch_size):
            batch_ids = job.target_member_ids[i:i + batch_size]
            
            # Fetch and process this batch
            batch_members = await self._fetch_batch_members(job, guild, batch_ids)
            await self._fetch_batch_status(job, batch_members)
            
            processed += len(batch_ids)
            
            # Progress reporting
            await self._report_progress(job, processed, total_targets, batch_size)
            
            # Inter-batch delay
            if processed < total_targets:
                await asyncio.sleep(random.uniform(1.0, 3.0))

    async def _fetch_batch_members(
        self, job: BulkVerificationJob, guild: discord.Guild, member_ids: list[int]
    ) -> list[discord.Member]:
        """Fetch Discord members for a batch of member IDs."""
        members = []
        for member_id in member_ids:
            try:
                member = guild.get_member(member_id)
                if member is None:
                    member = await guild.fetch_member(member_id)
                if member:
                    members.append(member)
            except (discord.NotFound, discord.HTTPException) as e:
                job.errors.append((member_id, f"User_{member_id}", f"Member fetch failed: {e!s}"[:200]))
                logger.debug(f"Failed to fetch member {member_id}: {e}")
        
        return members

    async def _fetch_batch_status(self, job: BulkVerificationJob, members: list[discord.Member]) -> None:
        """Fetch verification status rows for a batch of members.
        
        If job.recheck_rsi is True, performs live RSI verification for each member.
        """
        try:
            from helpers.bulk_check import fetch_status_rows
            batch_rows = await fetch_status_rows(members)
            
            # If RSI recheck is enabled, verify each member's RSI org status
            if job.recheck_rsi:
                batch_rows = await self._perform_rsi_recheck(batch_rows)
            
            job.status_rows.extend(batch_rows)
        except Exception as e:
            logger.exception(f"Error fetching status rows for batch: {e}")
            for member in members:
                job.errors.append((member.id, member.display_name, f"Status fetch failed: {e!s}"[:200]))

    async def _perform_rsi_recheck(self, status_rows: list) -> list:
        """Perform live RSI verification for each member in the batch using concurrent execution.
        
        Uses asyncio.gather to check all RSI handles in parallel, improving performance
        while maintaining proper error handling and logging for each user.
        
        Args:
            status_rows: List of StatusRow objects from DB
            
        Returns:
            Updated list of StatusRow objects with RSI recheck data
        """
        from helpers.bulk_check import StatusRow
        from verification.rsi_verification import is_valid_rsi_handle
        from helpers.http_helper import NotFoundError
        
        current_time = int(time.time())
        
        # Create concurrent tasks for all handles
        async def check_single_handle(row: StatusRow) -> RsiStatusResult:
            """Check a single RSI handle and return structured result."""
            if not row.rsi_handle:
                return RsiStatusResult(status="unknown", checked_at=current_time, error="No RSI handle")
            
            try:
                verify_value, _, _ = await is_valid_rsi_handle(
                    row.rsi_handle, 
                    self.bot.http_client
                )
                
                # Map verify_value to status string
                if verify_value == 1:
                    status = "main"
                elif verify_value == 2:
                    status = "affiliate"
                elif verify_value == 0:
                    status = "non_member"
                else:
                    status = "unknown"
                
                logger.debug(f"RSI check for user {row.user_id} ({row.rsi_handle}): verify_value={verify_value}, status={status}")
                return RsiStatusResult(status=status, checked_at=current_time)
                
            except NotFoundError:
                logger.debug(f"RSI handle not found for user {row.user_id}: {row.rsi_handle}")
                return RsiStatusResult(status="unknown", checked_at=current_time, error="Handle not found (404)")
            except Exception as e:
                logger.warning(f"RSI recheck failed for user {row.user_id} ({row.rsi_handle}): {e}")
                return RsiStatusResult(status="unknown", checked_at=current_time, error=str(e)[:200])
        
        # Execute all RSI checks concurrently
        tasks = [check_single_handle(row) for row in status_rows]
        rsi_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Build updated rows with RSI data
        updated_rows = []
        for row, result in zip(status_rows, rsi_results):
            # Handle unexpected exceptions from gather
            if isinstance(result, Exception):
                logger.error(f"Unexpected exception in RSI check for user {row.user_id}: {result}")
                result = RsiStatusResult(status="unknown", checked_at=current_time, error=f"Unexpected error: {result!s}"[:200])
            
            # Create new StatusRow with RSI data
            updated_row = StatusRow(
                user_id=row.user_id,
                username=row.username,
                rsi_handle=row.rsi_handle,
                membership_status=row.membership_status,
                last_updated=row.last_updated,
                voice_channel=row.voice_channel,
                rsi_status=result.status,
                rsi_checked_at=result.checked_at,
                rsi_error=result.error
            )
            updated_rows.append(updated_row)
        
        return updated_rows

    async def _report_progress(
        self, job: BulkVerificationJob, processed: int, total: int, batch_size: int
    ) -> None:
        """Send progress update to user if at reporting threshold."""
        if processed % (batch_size * 2) == 0 or processed >= total:
            try:
                await job.interaction.followup.send(
                    f"⏳ Processed {processed}/{total} users...",
                    ephemeral=True
                )
            except Exception as e:
                logger.debug(f"Failed to send progress update: {e}")

    async def _deliver_results(self, job: BulkVerificationJob, guild: discord.Guild) -> None:
        """Deliver final results to leadership channel (single post with embed + CSV)."""

        # Get initiator info
        try:
            invoker = await guild.fetch_member(job.invoker_id)
        except Exception:
            logger.warning(f"Failed to fetch invoker {job.invoker_id}")
            try:
                await job.interaction.followup.send(
                    "⚠️ Could not post results to leadership chat.",
                    ephemeral=True
                )
            except Exception:
                pass
            return

        # Build the detailed embed (always show full details)
        # Create member list for embed generation
        members = []
        for row in job.status_rows:
            if member := guild.get_member(row.user_id):
                members.append(member)

        try:
            from helpers.bulk_check import build_summary_embed
            embed = build_summary_embed(
                invoker=invoker,
                members=members,
                rows=job.status_rows,
                truncated_count=0,
                scope_label=job.scope_label,
                scope_channel=job.scope_channel
            )
        except Exception as e:
            logger.exception(f"Error building summary embed: {e}")
            try:
                await job.interaction.followup.send(
                    f"❌ Error building results: {e!s}",
                    ephemeral=True
                )
            except Exception:
                pass
            return

        # Generate CSV with guild name and invoker name
        try:
            from helpers.bulk_check import write_csv
            filename, content_bytes = await write_csv(
                job.status_rows,
                guild_name=guild.name,
                invoker_name=invoker.display_name
            )
        except Exception as e:
            logger.exception(f"Error generating CSV: {e}")
            # Create minimal error CSV
            content_bytes = b"user_id,username,rsi_handle,membership_status,last_updated,voice_channel\n"
            filename = f"verify_bulk_error_{int(time.time())}.csv"

        # Send to leadership channel (single post: embed + CSV)
        try:
            from helpers.announcement import send_admin_bulk_check_summary
            channel_name = await send_admin_bulk_check_summary(
                self.bot,
                guild=guild,
                invoker=invoker,
                scope_label=job.scope_label,
                scope_channel=job.scope_channel,
                embed=embed,
                csv_bytes=content_bytes,
                csv_filename=filename
            )

            logger.info(f"Posted bulk check results to #{channel_name} for job {job.job_id}")

            # Send success ack to invoker
            try:
                await job.interaction.followup.send(
                    f"✅ Posted results to #{channel_name}",
                    ephemeral=True
                )
            except Exception as e:
                logger.debug(f"Could not send success ack: {e}")

        except Exception as e:
            logger.exception(f"Error posting to leadership channel: {e}")
            try:
                await job.interaction.followup.send(
                    f"❌ Error posting results to leadership chat: {e!s}",
                    ephemeral=True
                )
            except Exception:
                pass


async def initialize(bot: "commands.Bot") -> None:
    """Initialize the verification bulk service."""
    return VerificationBulkService(bot)
