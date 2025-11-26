"""
Refactored admin cog with service integration and health monitoring.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

import discord
from discord import app_commands
from discord.ext import commands

from helpers.decorators import require_admin, require_bot_admin
from utils.logging import get_logger

logger = get_logger(__name__)


class ConfigSchema:
    """Configuration schema defining allowed keys, types, and descriptions."""

    ALLOWED_KEYS: ClassVar[dict[str, dict[str, Any]]] = {
        "roles.bot_admins": {
            "type": list,
            "element_type": int,
            "description": "List of bot admin role IDs",
            "json_example": "[123456789, 987654321]",
            "default": [],
        },
        "roles.lead_moderators": {
            "type": list,
            "element_type": int,
            "description": "List of lead moderator role IDs",
            "json_example": "[123456789, 987654321]",
            "default": [],
        },
        "channels.voice_category_id": {
            "type": int,
            "description": "Voice category channel ID for creating voice channels",
            "json_example": "123456789",
            "default": None,
        },
        "voice.cooldown_seconds": {
            "type": int,
            "description": "Voice channel creation cooldown in seconds",
            "json_example": "30",
            "min": 0,
            "max": 3600,
            "default": 60,
        },
        "voice.join_to_create_channels": {
            "type": list,
            "element_type": int,
            "description": "List of join-to-create channel IDs",
            "json_example": "[123456789, 987654321]",
            "default": [],
        },
        "voice.user_limit": {
            "type": int,
            "description": "Default user limit for voice channels",
            "json_example": "10",
            "min": 0,
            "max": 99,
            "default": 0,
        },
        "voice.default_bitrate": {
            "type": int,
            "description": "Default bitrate for voice channels (kbps)",
            "json_example": "64",
            "min": 8,
            "max": 384,
            "default": 64,
        },
        "roles.admin": {
            "type": int,
            "description": "Single admin role ID (deprecated - use roles.bot_admins)",
            "json_example": "123456789",
            "default": None,
        },
        "roles.moderator": {
            "type": int,
            "description": "Single moderator role ID (deprecated - use roles.lead_moderators)",
            "json_example": "123456789",
            "default": None,
        },
        "channels.logs": {
            "type": int,
            "description": "Log channel ID",
            "json_example": "123456789",
            "default": None,
        },
        "channels.announcements": {
            "type": int,
            "description": "Announcements channel ID",
            "json_example": "123456789",
            "default": None,
        },
        "features.auto_role": {
            "type": bool,
            "description": "Enable automatic role assignment",
            "json_example": "true",
            "default": False,
        },
        "features.welcome_messages": {
            "type": bool,
            "description": "Enable welcome messages",
            "json_example": "true",
            "default": True,
        },
        "settings.prefix": {
            "type": str,
            "description": "Command prefix",
            "json_example": '"!"',
            "default": "!",
        },
        "settings.timezone": {
            "type": str,
            "description": "Server timezone",
            "json_example": '"UTC"',
            "default": "UTC",
        },
    }

    @classmethod
    def get_key_choices(cls) -> list[app_commands.Choice[str]]:
        """Get app_commands.Choice objects for all allowed keys."""
        return [
            app_commands.Choice(name=f"{key} - {info['description']}", value=key)
            for key, info in cls.ALLOWED_KEYS.items()
        ]

    @classmethod
    def get_type_for_key(cls, key: str) -> type:
        """Get the expected type for a configuration key."""
        return cls.ALLOWED_KEYS.get(key, {}).get("type", str)

    @classmethod
    def get_validation_info(cls, key: str) -> dict[str, Any]:
        """Get validation constraints for a key."""
        return cls.ALLOWED_KEYS.get(key, {})

    @classmethod
    def get_value_hint(cls, key: str) -> str:
        """Get a value hint showing expected JSON format."""
        if key not in cls.ALLOWED_KEYS:
            return "Unknown key"

        config_info = cls.ALLOWED_KEYS[key]
        expected_type = config_info["type"]
        example = config_info.get("json_example", "")

        if expected_type is list:
            element_type = config_info.get("element_type", str).__name__
            return f"Expected: JSON array of {element_type} - Example: {example}"
        elif expected_type is int:
            constraints = []
            if "min" in config_info:
                constraints.append(f"min: {config_info['min']}")
            if "max" in config_info:
                constraints.append(f"max: {config_info['max']}")
            constraint_str = f" ({', '.join(constraints)})" if constraints else ""
            return f"Expected: integer{constraint_str} - Example: {example}"
        elif expected_type is bool:
            return f"Expected: boolean (true/false) - Example: {example}"
        elif expected_type is str:
            return f"Expected: string - Example: {example}"
        else:
            return f"Expected: {expected_type.__name__} - Example: {example}"

    @classmethod
    def validate_value(cls, key: str, value: Any) -> tuple[bool, str, Any]:
        """
        Validate a value for a given key.

        Returns:
            (is_valid, error_message, coerced_value)
        """
        if key not in cls.ALLOWED_KEYS:
            return False, f"Unknown configuration key: {key}", None

        config_info = cls.ALLOWED_KEYS[key]
        expected_type = config_info["type"]

        # Try to coerce the value to the expected type
        try:
            if expected_type is bool:
                # Handle boolean conversion specially
                if isinstance(value, str):
                    if value.lower() in ("true", "1", "yes", "on", "enabled"):
                        coerced_value = True
                    elif value.lower() in ("false", "0", "no", "off", "disabled"):
                        coerced_value = False
                    else:
                        return (
                            False,
                            "Invalid boolean value. Use 'true' or 'false'",
                            None,
                        )
                else:
                    coerced_value = bool(value)
            elif expected_type is int:
                coerced_value = int(value)
                # Check range constraints
                if "min" in config_info and coerced_value < config_info["min"]:
                    return False, f"Value must be at least {config_info['min']}", None
                if "max" in config_info and coerced_value > config_info["max"]:
                    return False, f"Value must be at most {config_info['max']}", None
            elif expected_type is str:
                coerced_value = str(value)
            elif expected_type is list:
                # Handle list types with JSON parsing
                if isinstance(value, str):
                    try:
                        import json

                        coerced_value = json.loads(value)
                        if not isinstance(coerced_value, list):
                            return (
                                False,
                                f"Expected a JSON array, got {type(coerced_value).__name__}",
                                None,
                            )
                    except json.JSONDecodeError as e:
                        return False, f"Invalid JSON array: {e}", None
                elif isinstance(value, list):
                    coerced_value = value
                else:
                    return (
                        False,
                        f"Expected a JSON array or list, got {type(value).__name__}",
                        None,
                    )

                # Validate element types if specified
                if "element_type" in config_info:
                    element_type = config_info["element_type"]
                    try:
                        coerced_value = [element_type(item) for item in coerced_value]
                    except (ValueError, TypeError) as e:
                        return (
                            False,
                            f"List contains invalid {element_type.__name__} values: {e}",
                            None,
                        )
            else:
                coerced_value = value

            return True, "", coerced_value

        except (ValueError, TypeError) as e:
            return (
                False,
                f"Cannot convert '{value}' to {expected_type.__name__}: {e}",
                None,
            )


class AdminCog(commands.Cog):
    """
    Administrative commands with service integration.

    Provides health monitoring, status reporting, and administrative
    functions using the service architecture.
    """

    def __init__(self, bot) -> None:
        self.bot = bot
        self.logger = get_logger(__name__)
        # Track in-flight recheck operations to prevent duplicate execution
        self._recheck_in_flight: set[int] = set()

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Check if user has admin permissions."""
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return False

        return await self.bot.has_admin_permissions(ctx.author)

    @app_commands.command(
        name="reset-all", description="Reset verification timers for all members."
    )
    @app_commands.guild_only()
    @require_bot_admin()
    async def reset_all(self, interaction: discord.Interaction) -> None:
        """
        Reset verification timers for all members. Bot Admins only.
        """
        from helpers.discord_api import send_message
        from helpers.rate_limiter import reset_all_attempts
        from helpers.token_manager import clear_all_tokens

        self.logger.info(
            f"'reset-all' command triggered by user {interaction.user.id}."
        )
        
        # Defer immediately before async operations
        await interaction.response.defer(ephemeral=True)

        await reset_all_attempts()
        clear_all_tokens()

        await interaction.followup.send(
            "✅ Reset verification timers for all members.", ephemeral=True
        )

        self.logger.info(
            "Reset-all command completed successfully.",
            extra={"user_id": interaction.user.id},
        )

    @app_commands.command(
        name="reset-user", description="Reset verification timer for a specific user."
    )
    @app_commands.describe(member="The member whose timer you want to reset.")
    @app_commands.guild_only()
    @require_admin()
    async def reset_user(
        self, interaction: discord.Interaction, member: discord.Member
    ) -> None:
        """
        Reset a specific user's verification timer. Bot Admins and Lead Moderators.
        """
        from helpers.discord_api import send_message
        from helpers.rate_limiter import reset_attempts
        from helpers.token_manager import clear_token

        self.logger.info(
            f"'reset-user' command triggered by user {interaction.user.id} for member {member.id}."
        )
        
        # Defer immediately before async operations
        await interaction.response.defer(ephemeral=True)

        await reset_attempts(member.id)
        clear_token(member.id)

        await interaction.followup.send(
            f"✅ Reset verification timer for {member.mention}.",
            ephemeral=True,
        )

        self.logger.info(
            "Reset-user command completed successfully.",
            extra={"user_id": interaction.user.id, "target_user_id": member.id},
        )

    @app_commands.command(
        name="flush-announcements",
        description="Force flush pending announcement queue immediately."
    )
    @app_commands.guild_only()
    @require_bot_admin()
    async def flush_announcements(self, interaction: discord.Interaction) -> None:
        """
        Force flush the pending announcement queue immediately.
        
        This will post all pending member join/promotion announcements to the
        public announcement channel instead of waiting for the daily scheduled time
        or threshold trigger. Bot Admins only.
        """
        from helpers.discord_api import send_message
        
        self.logger.info(
            f"'flush-announcements' command triggered by user {interaction.user.id} ({interaction.user.display_name})."
        )

        await interaction.response.defer(ephemeral=True)

        try:
            # Get the BulkAnnouncer cog
            announcer = self.bot.get_cog("BulkAnnouncer")
            if not announcer:
                await interaction.followup.send(
                    "❌ BulkAnnouncer cog not loaded. Cannot flush announcements.",
                    ephemeral=True
                )
                self.logger.error("BulkAnnouncer cog not found when flush-announcements was called")
                return

            # Get pending count before flushing
            pending_count = await announcer._count_pending()
            
            if pending_count == 0:
                await interaction.followup.send(
                    "ℹ️ No pending announcements in queue.",
                    ephemeral=True
                )
                self.logger.info(
                    "flush-announcements: no pending announcements",
                    extra={"user_id": interaction.user.id}
                )
                return

            # Flush the queue
            self.logger.info(
                f"flush-announcements: flushing {pending_count} pending events",
                extra={"user_id": interaction.user.id}
            )
            
            sent = await announcer.flush_pending()
            
            if sent:
                await interaction.followup.send(
                    f"✅ Successfully flushed announcement queue! Posted {pending_count} pending event(s) to public announcement channels.",
                    ephemeral=True
                )
                self.logger.info(
                    f"flush-announcements: successfully flushed {pending_count} events",
                    extra={"user_id": interaction.user.id}
                )
            else:
                await interaction.followup.send(
                    f"⚠️ Flush completed but no announcements were sent. Check that public announcement channels are configured.",
                    ephemeral=True
                )
                self.logger.warning(
                    f"flush-announcements: flush returned False (no announcements sent) despite {pending_count} pending",
                    extra={"user_id": interaction.user.id}
                )

        except Exception as e:
            await interaction.followup.send(
                f"❌ Failed to flush announcements: {e}",
                ephemeral=True
            )
            self.logger.exception(
                f"flush-announcements command failed: {e}",
                extra={"user_id": interaction.user.id}
            )

    @app_commands.command(name="view-logs", description="View recent bot logs.")
    @app_commands.guild_only()
    @require_admin()
    async def view_logs(self, interaction: discord.Interaction) -> None:
        """View recent bot logs with dual delivery - channel preview and full content via DM."""
        self.logger.info(
            f"'view-logs' command triggered by user {interaction.user.id}."
        )

        try:
            await interaction.response.defer(ephemeral=True)

            log_file = Path("logs/bot.log")
            if not log_file.exists():
                await interaction.followup.send(
                    "❌ Log file not found.", ephemeral=True
                )
                return

            # Read the entire log file for DM and last lines for channel
            with open(log_file, encoding="utf-8") as f:
                all_lines = f.readlines()

            if not all_lines:
                await interaction.followup.send("📋 Log file is empty.", ephemeral=True)
                return

            # Get last ~50 lines for preview display
            recent_lines = all_lines[-50:] if len(all_lines) > 50 else all_lines
            recent_content = "".join(recent_lines)

            # Always provide dual delivery: channel preview + DM full content
            max_preview_length = 1000  # Shortened for better preview experience

            # Create channel preview (always truncated for consistency)
            if len(recent_content) > max_preview_length:
                preview_content = (
                    recent_content[:max_preview_length] + "... (preview truncated)"
                )
            else:
                preview_content = (
                    recent_content + "\n(showing recent entries - full log sent via DM)"
                )

            # Create embed for channel preview
            embed = discord.Embed(
                title="📋 Bot Logs Preview (Last ~50 lines)",
                description=f"```\n{preview_content}\n```",
                color=discord.Color.blue(),
                timestamp=datetime.now(UTC),
            )
            embed.set_footer(text="Full log file sent via DM")

            await interaction.followup.send(embed=embed, ephemeral=True)

            # Always try to send full content as DM
            dm_success = False
            try:
                # Create a file-like object from the log content
                full_content = "".join(all_lines)

                # If content is extremely large, create a text file
                if len(full_content) > 8000:
                    import io

                    log_bytes = full_content.encode("utf-8")
                    file_obj = discord.File(
                        io.BytesIO(log_bytes),
                        filename=f"bot_logs_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.txt",
                    )

                    await interaction.user.send(
                        content="📋 **Full Bot Log File**\n"
                        f"Generated on {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
                        f"Total lines: {len(all_lines)}",
                        file=file_obj,
                    )
                    dm_success = True
                else:
                    # Send as text if not too large
                    dm_embed = discord.Embed(
                        title="📋 Full Bot Log",
                        description=f"```\n{full_content}\n```",
                        color=discord.Color.blue(),
                        timestamp=datetime.now(UTC),
                    )
                    await interaction.user.send(embed=dm_embed)
                    dm_success = True

            except discord.Forbidden:
                # User has DMs closed to non-friends
                pass
            except discord.HTTPException as dm_error:
                # Other Discord API errors
                self.logger.warning(
                    f"Could not DM full logs to admin {interaction.user.id}: {dm_error}"
                )
            except Exception as e:
                # Other unexpected errors
                self.logger.warning(
                    f"Failed to send DM to admin {interaction.user.id}: {e}"
                )

            # If DM failed, send follow-up notice
            if not dm_success:
                await interaction.followup.send(
                    "⚠️ **Full logs couldn't be sent via DM** - your DMs may be closed to non-friends. "
                    "Only the preview is shown above. Please enable DMs from server members to receive full logs.",
                    ephemeral=True,
                )

        except Exception as e:
            self.logger.exception("Error in view-logs command", exc_info=e)
            await interaction.followup.send(
                f"❌ Error retrieving logs: {e!s}", ephemeral=True
            )

    @app_commands.command(
        name="recheck-user",
        description="Force a verification re-check for a user (Bot Admins & Lead Moderators).",
    )
    @app_commands.describe(member="The member to recheck.")
    @app_commands.guild_only()
    @require_admin()
    async def recheck_user(
        self, interaction: discord.Interaction, member: discord.Member
    ) -> None:
        """Force a verification re-check for a user."""
        # Check if recheck is already in progress for this user
        if member.id in self._recheck_in_flight:
            await interaction.response.send_message(
                f"⏳ Recheck is already in progress for {member.mention}. Please wait.",
                ephemeral=True,
            )
            return

        # Add user to in-flight set
        self._recheck_in_flight.add(member.id)

        try:
            from helpers.announcement import (
                canonicalize_status_for_display,
                enqueue_verification_event,
                send_admin_recheck_notification,
            )
            from helpers.leadership_log import ChangeSet, EventType
            from helpers.role_helper import reverify_member
            from helpers.snapshots import diff_snapshots, snapshot_member_state
            from helpers.task_queue import flush_tasks
            from services.db.database import Database

            self.logger.info(
                f"'recheck-user' command triggered by user {interaction.user.id} for member {member.id}. "
                f"Guild: {interaction.guild.name} ({interaction.guild_id}), "
                f"member.guild: {member.guild.name} ({member.guild.id})"
            )

            await interaction.response.defer(ephemeral=True)

            # Fetch existing verification record
            async with Database.get_connection() as db:
                cursor = await db.execute(
                    "SELECT rsi_handle FROM verification WHERE user_id = ?",
                    (member.id,),
                )
                row = await cursor.fetchone()

            if not row:
                await interaction.followup.send(
                    f"❌ {member.mention} is not verified.", ephemeral=True
                )
                return

            rsi_handle = row[0]

            # Snapshot before reverify
            before_snap = await snapshot_member_state(self.bot, member)

            # Attempt re-verification - pass the actual bot instance
            try:
                result = await reverify_member(member, rsi_handle, self.bot)
            except Exception as e:
                self.logger.exception("Error during reverification", exc_info=e)
                await interaction.followup.send(
                    f"❌ Error during re-verification: {e!s}", ephemeral=True
                )
                return

            success, role_assignment_result, message = result
            if not success:
                # Log the error and try to DM the admin with helpful info
                error_msg = f"Re-verification failed for {member.mention} (RSI: {rsi_handle}): {message}"
                self.logger.error(error_msg)

                try:
                    # Try to send a DM to the admin with more details
                    dm_msg = (
                        f"⚠️ **RSI Re-verification Failed**\n\n"
                        f"**Member:** {member.mention} ({member.display_name})\n"
                        f"**RSI Handle:** `{rsi_handle}`\n"
                        f"**Error:** {message}\n"
                        f"**Result:** {role_assignment_result}\n\n"
                        f"Please check the logs for more details or manually verify the RSI handle."
                    )
                    await interaction.user.send(dm_msg)
                except Exception as dm_error:
                    self.logger.warning(
                        f"Could not DM admin about recheck failure: {dm_error}"
                    )

                await interaction.followup.send(
                    f"❌ Re-verification failed: {message}", ephemeral=True
                )
                return

            # Flush task queue to apply changes
            await flush_tasks()

            # Snapshot after
            after_snap = await snapshot_member_state(self.bot, member)
            diff = diff_snapshots(before_snap, after_snap)

            # Log changes (removed duplicate post_if_changed call to prevent duplicate admin messages)
            # The send_admin_recheck_notification below handles all admin announcement posting
            try:
                cs = ChangeSet(
                    user_id=member.id,
                    event=EventType.ADMIN_CHECK,
                    initiator_kind="Admin",
                    initiator_name=interaction.user.display_name,
                    notes=f"Manual recheck by {interaction.user.display_name}",
                    guild_id=member.guild.id if member.guild else None,
                )
                for k, v in diff.items():
                    setattr(cs, k, v)
                # Removed post_if_changed call to prevent duplicate admin messages
                # All admin notifications are now handled by send_admin_recheck_notification
            except Exception as e:
                self.logger.debug(f"Leadership log changeset creation failed: {e}")

            # Handle admin announcements and bulk announcer for recheck results
            admin_response_message = ""
            try:
                # Extract old and new status from result
                old_status_raw = None
                new_status_raw = None

                if success and role_assignment_result:
                    # role_assignment_result is the tuple (old_status, new_status) from assign_roles
                    if (
                        isinstance(role_assignment_result, tuple | list)
                        and len(role_assignment_result) >= 2
                    ):
                        old_status_raw, new_status_raw = (
                            role_assignment_result[0],
                            role_assignment_result[1],
                        )
                    else:
                        # Fallback: try to get from diff
                        old_status_raw = getattr(diff, "status_before", None)
                        new_status_raw = getattr(diff, "status_after", None)
                else:
                    # Fallback: get from diff snapshots
                    old_status_raw = getattr(diff, "status_before", None)
                    new_status_raw = getattr(diff, "status_after", None)

                # Use helper functions for canonical display
                old_status_pretty = canonicalize_status_for_display(old_status_raw)
                new_status_pretty = canonicalize_status_for_display(new_status_raw)

                # Send admin notification to admin announcements channel using updated helper
                notification_sent, status_changed = (
                    await send_admin_recheck_notification(
                        bot=self.bot,
                        admin_display_name=interaction.user.display_name,
                        member=member,
                        old_status=old_status_raw or "unknown",
                        new_status=new_status_raw or "unknown",
                    )
                )

                # Note: enqueue_verification_event() is called by assign_roles() -> reverify_member()
                # so we don't need to call it again here (avoids redundant DB operations)
                if status_changed:
                    admin_response_message = f"✅ Recheck complete: {member.mention} status changed from {old_status_pretty} to {new_status_pretty}"
                else:
                    admin_response_message = f"ℹ️ Recheck complete: {member.mention} no status change ({old_status_pretty})"

                if not notification_sent:
                    admin_response_message += " (Admin notification failed to send)"

            except Exception as e:
                self.logger.warning(
                    f"Failed to handle admin recheck announcements: {e}"
                )
                admin_response_message = f"✅ Re-verification completed for {member.mention}, but announcement handling failed"

            await interaction.followup.send(admin_response_message, ephemeral=True)

        except Exception as e:
            self.logger.exception("Error in recheck-user command", exc_info=e)
            await interaction.followup.send(
                f"❌ Error during re-check: {e!s}", ephemeral=True
            )
        finally:
            # Always remove user from in-flight set when recheck completes or fails
            self._recheck_in_flight.discard(member.id)

    @reset_all.error
    @reset_user.error
    @recheck_user.error
    @view_logs.error
    async def admin_command_error(
        self, interaction: discord.Interaction, error
    ) -> None:
        """Handle errors in admin commands."""
        self.logger.error(f"Admin command error: {error}")
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"❌ Command error: {error!s}", ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ Command error: {error!s}", ephemeral=True
                )
        except discord.HTTPException:
            pass  # Ignore if we can't send error message

    @app_commands.command(
        name="status", description="Show detailed bot health and status information"
    )
    @app_commands.describe(detailed="Show detailed service information")
    @require_admin()
    async def status(
        self, interaction: discord.Interaction, detailed: bool = False
    ) -> None:
        """Show bot status and health metrics."""
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            # Get comprehensive health report
            health_report = await self.bot.services.health.run_health_checks(
                self.bot, self.bot.services.get_all_services()
            )
            # Create status embed
            embed = discord.Embed(
                title="🤖 Bot Status",
                color=self._get_status_color(health_report["overall_status"]),
                timestamp=discord.utils.utcnow(),
            )
            # Basic status info
            embed.add_field(
                name="Overall Status",
                value=self._format_status(health_report["overall_status"]),
                inline=True,
            )

            embed.add_field(name="Uptime", value=self.bot.uptime, inline=True)

            embed.add_field(
                name="Guilds",
                value=str(health_report["discord"]["guilds"]),
                inline=True,
            )

            # System metrics
            system = health_report["system"]
            embed.add_field(
                name="💻 System",
                value=f"CPU: {system['cpu_percent']:.1f}%\\n"
                f"Memory: {system['memory_mb']:.1f} MB\\n"
                f"Threads: {system['threads']}",
                inline=True,
            )

            # Discord metrics
            discord_info = health_report["discord"]
            embed.add_field(
                name="🔗 Discord",
                value=f"Latency: {discord_info['latency_ms']}ms\\n"
                f"Users: {discord_info['users']}\\n"
                f"Ready: {'✅' if discord_info['is_ready'] else '❌'}",
                inline=True,
            )

            # Database status
            db = health_report["database"]
            if db["connected"]:
                embed.add_field(name="🗄️ Database", value="✅ Connected", inline=True)
            else:
                embed.add_field(
                    name="🗄️ Database",
                    value=f"❌ Error: {db.get('error', 'Unknown')}",
                    inline=True,
                )

            # Bot metrics
            metrics = health_report.get("metrics", {})
            if metrics:
                embed.add_field(
                    name="📊 Metrics",
                    value=f"Commands: {metrics.get('commands_processed', 0)}\\n"
                    f"Events: {metrics.get('events_processed', 0)}\\n"
                    f"Errors: {metrics.get('errors_encountered', 0)}\\n"
                    f"Voice Channels: {metrics.get('voice_channels_created', 0)}",
                    inline=True,
                )

            # Service status
            services = health_report.get("services", {})
            service_status = []
            for service_name, service_health in services.items():
                status = service_health.get("status", "unknown")
                emoji = (
                    "✅"
                    if status == "healthy"
                    else "⚠️" if status == "degraded" else "❌"
                )
                service_status.append(f"{emoji} {service_name}")

            if service_status:
                embed.add_field(
                    name="🔧 Services", value="\\n".join(service_status), inline=True
                )

            # Detailed service info if requested
            if detailed and services:
                for service_name, service_health in services.items():
                    if service_name in ["config", "guild", "voice"]:
                        details = []
                        for key, value in service_health.items():
                            if key not in ["service", "status", "initialized"]:
                                details.append(f"{key}: {value}")

                        if details:
                            embed.add_field(
                                name=f"📋 {service_name.title()} Details",
                                value="\\n".join(
                                    details[:5]
                                ),  # Limit to avoid embed limits
                                inline=False,
                            )

            embed.set_footer(text=f"Requested by {interaction.user.display_name}")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.exception("Error in status command", exc_info=e)
            await interaction.followup.send(
                f"❌ Error retrieving status: {e!s}", ephemeral=True
            )

    @app_commands.command(
        name="guild-config", description="Show configuration for this guild"
    )
    @require_admin()
    async def guild_config(self, interaction: discord.Interaction) -> None:
        """Show guild-specific configuration."""
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            config = await self.bot.get_guild_config(interaction.guild.id)

            # Check if config is empty or None
            if not config:
                await interaction.followup.send(
                    "⚠️ No configuration found for this guild. "
                    "Use `/set-config` to add settings.",
                    ephemeral=True,
                )
                return

            embed = discord.Embed(
                title="⚙️ Guild Configuration",
                description=f"Configuration for **{interaction.guild.name}**",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow(),
            )

            # Roles configuration
            roles = config.get("roles", {})
            if roles:
                role_info = []
                for role_key, role_id in roles.items():
                    if isinstance(role_id, list):
                        role_names = []
                        for rid in role_id:
                            role = interaction.guild.get_role(rid)
                            role_names.append(role.name if role else f"Unknown ({rid})")
                        role_info.append(f"• {role_key}: {', '.join(role_names)}")
                    else:
                        role = interaction.guild.get_role(role_id)
                        role_name = role.name if role else f"Unknown ({role_id})"
                        role_info.append(f"• {role_key}: {role_name}")

                embed.add_field(
                    name="🎭 Roles",
                    value="\\n".join(role_info[:10]),  # Limit to avoid embed limits
                    inline=False,
                )
            else:
                embed.add_field(
                    name="🎭 Roles", value="No roles configured", inline=False
                )

            # Channels configuration
            channels = config.get("channels", {})
            if channels:
                channel_info = []
                for channel_key, channel_id in channels.items():
                    channel = interaction.guild.get_channel(channel_id)
                    channel_name = (
                        channel.name if channel else f"Unknown ({channel_id})"
                    )
                    channel_info.append(f"• {channel_key}: #{channel_name}")

                embed.add_field(
                    name="📺 Channels", value="\\n".join(channel_info), inline=False
                )
            else:
                embed.add_field(
                    name="📺 Channels", value="No channels configured", inline=False
                )

            # Voice settings with better error handling
            try:
                voice_cooldown = await self.bot.services.config.get(
                    interaction.guild.id,
                    "voice.cooldown_seconds",
                    default=60,
                    parser=int,
                )

                voice_info = f"• Cooldown: {voice_cooldown}s"

                # Get additional voice settings if they exist
                voice_limit = await self.bot.services.config.get(
                    interaction.guild.id, "voice.user_limit", parser=int
                )
                if voice_limit:
                    voice_info += f"\\n• User Limit: {voice_limit}"

                embed.add_field(name="🔊 Voice Settings", value=voice_info, inline=True)

            except Exception as voice_error:
                self.logger.warning(f"Error getting voice settings: {voice_error}")
                embed.add_field(
                    name="🔊 Voice Settings",
                    value="Error loading voice settings",
                    inline=True,
                )

            embed.set_footer(text=f"Requested by {interaction.user.display_name}")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            self.logger.exception("Error in guild-config command", exc_info=e)
            await interaction.followup.send(
                "❌ An error occurred while retrieving the guild configuration. "
                "Please try again or contact support if the issue persists.",
                ephemeral=True,
            )

    async def key_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Provide autocomplete suggestions for configuration keys."""
        choices = []

        for key, config_info in ConfigSchema.ALLOWED_KEYS.items():
            if (
                not current
                or current.lower() in key.lower()
                or current.lower() in config_info["description"].lower()
            ):
                choices.append(
                    app_commands.Choice(
                        name=f"{key} - {config_info['description']}", value=key
                    )
                )

        # Limit to 25 choices (Discord limit)
        return choices[:25]

    async def value_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Provide autocomplete suggestions for configuration values based on the selected key."""
        # Get the key parameter from the interaction
        key = None
        for option in interaction.data.get("options", []):
            if option["name"] == "key":
                key = option["value"]
                break

        if not key or key not in ConfigSchema.ALLOWED_KEYS:
            return [app_commands.Choice(name="Select a key first", value="")]

        config_info = ConfigSchema.ALLOWED_KEYS[key]
        expected_type = config_info["type"]
        description = config_info["description"]

        choices = []

        # Add value hint as first choice
        hint = ConfigSchema.get_value_hint(key)
        if not current:
            choices.append(
                app_commands.Choice(
                    name=f"💡 {hint}", value=config_info.get("json_example", "")
                )
            )

        if expected_type is bool:
            # Boolean suggestions
            suggestions = ["true", "false"]
            for suggestion in suggestions:
                if current.lower() in suggestion.lower():
                    choices.append(
                        app_commands.Choice(
                            name=f"{suggestion} - {description}", value=suggestion
                        )
                    )
        elif expected_type is list:
            # List suggestions with JSON examples
            example = config_info.get("json_example", "[]")
            element_type = config_info.get("element_type", str).__name__

            suggestions = [example, "[]"]  # Empty list as option
            if "role" in key.lower() or "channel" in key.lower():
                suggestions.extend(["[123456789]", "[123456789, 987654321]"])

            for suggestion in suggestions:
                if not current or current in suggestion:
                    choices.append(
                        app_commands.Choice(
                            name=f"{suggestion} - JSON array of {element_type}",
                            value=suggestion,
                        )
                    )
        elif expected_type is int:
            # Integer suggestions with constraints
            default_val = config_info.get("default", 0)
            min_val = config_info.get("min")
            max_val = config_info.get("max")

            suggestions = [str(default_val)]
            if min_val is not None:
                suggestions.append(str(min_val))
            if max_val is not None:
                suggestions.append(str(max_val))

            # Add some common values based on the key type
            if "cooldown" in key:
                suggestions.extend(["30", "60", "120", "300"])
            elif "limit" in key:
                suggestions.extend(["5", "10", "20", "50"])
            elif "bitrate" in key:
                suggestions.extend(["64", "128", "256", "384"])

            for suggestion in set(suggestions):
                if not current or current in suggestion:
                    range_info = ""
                    if min_val is not None and max_val is not None:
                        range_info = f" (range: {min_val}-{max_val})"
                    elif min_val is not None:
                        range_info = f" (min: {min_val})"
                    elif max_val is not None:
                        range_info = f" (max: {max_val})"

                    choices.append(
                        app_commands.Choice(
                            name=f"{suggestion}{range_info} - {description}",
                            value=suggestion,
                        )
                    )
        elif expected_type is str:
            # String suggestions
            default_val = config_info.get("default", "")
            if default_val:
                choices.append(
                    app_commands.Choice(
                        name=f"{default_val} (default) - {description}",
                        value=str(default_val),
                    )
                )

            # Add some common string values based on key type
            if "prefix" in key:
                common_values = ["!", "?", "/", "$", "%"]
            elif "timezone" in key:
                common_values = [
                    "UTC",
                    "America/New_York",
                    "Europe/London",
                    "Asia/Tokyo",
                ]
            else:
                common_values = []

            for value in common_values:
                if not current or current.lower() in value.lower():
                    choices.append(
                        app_commands.Choice(
                            name=f"{value} - {description}", value=value
                        )
                    )

        # Limit to 25 choices (Discord limit)
        return choices[:25]

    @app_commands.command(
        name="set-config", description="Set a configuration value for this guild"
    )
    @app_commands.describe(
        key="Configuration key to set",
        value="JSON value (int, string, boolean, or array) - Format varies by key",
    )
    @app_commands.autocomplete(key=key_autocomplete)
    @app_commands.autocomplete(value=value_autocomplete)
    @require_bot_admin()
    async def set_config(
        self, interaction: discord.Interaction, key: str, value: str
    ) -> None:
        """Set a guild configuration value."""
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            # Validate the key and value using our schema
            is_valid, error_message, coerced_value = ConfigSchema.validate_value(
                key, value
            )

            if not is_valid:
                await interaction.followup.send(
                    f"❌ **Validation Error**\n{error_message}", ephemeral=True
                )
                return

            # Set the configuration using the guild config service
            await self.bot.services.config.set(interaction.guild.id, key, coerced_value)

            # Retrieve the effective stored value using typed parsing
            config_info = ConfigSchema.get_validation_info(key)
            expected_type = config_info.get("type", str)

            # Get the parser function based on type
            parser = None
            if expected_type is int:
                parser = int
            elif expected_type is list:
                element_type = config_info.get("element_type", str)
                if element_type is int:

                    def parser(x):
                        return (
                            [int(i) for i in json.loads(x)] if isinstance(x, str) else x
                        )

                else:

                    def parser(x):
                        return json.loads(x) if isinstance(x, str) else x

            elif expected_type is bool:

                def parser(x):
                    return json.loads(x.lower()) if isinstance(x, str) else bool(x)

            # Get the effective stored value using the guild config service with parser
            stored_value = await self.bot.services.config.get(
                interaction.guild.id, key, parser=parser
            )

            # Create success embed with type information
            type_name = (
                expected_type.__name__
                if hasattr(expected_type, "__name__")
                else str(expected_type)
            )
            if expected_type is list:
                element_type = config_info.get("element_type", str).__name__
                type_name = f"list[{element_type}]"

            embed = discord.Embed(
                title="✅ Configuration Updated",
                description="Successfully updated configuration setting",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow(),
            )

            embed.add_field(name="Key", value=f"`{key}`", inline=True)
            embed.add_field(
                name="Parsed Value", value=f"`{coerced_value}`", inline=True
            )
            embed.add_field(
                name="Stored Value",
                value=f"`{stored_value}` ({type_name})",
                inline=True,
            )
            embed.add_field(
                name="Description",
                value=config_info.get("description", "No description"),
                inline=False,
            )

            embed.set_footer(text=f"Updated by {interaction.user.display_name}")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            self.logger.exception("Error in set-config command", exc_info=e)
            await interaction.followup.send(
                "❌ **Configuration Error**\\n"
                "An unexpected error occurred while updating the configuration. "
                "Please try again or contact support if the issue persists.",
                ephemeral=True,
            )

    def _get_status_color(self, status: str) -> discord.Color:
        """Get color for status embed based on overall status."""
        if status == "healthy":
            return discord.Color.green()
        elif status == "degraded":
            return discord.Color.yellow()
        else:
            return discord.Color.red()

    def _format_status(self, status: str) -> str:
        """Format status with emoji."""
        if status == "healthy":
            return "✅ Healthy"
        elif status == "degraded":
            return "⚠️ Degraded"
        else:
            return "❌ Unhealthy"


async def setup(bot) -> None:
    """Setup function for the cog."""
    await bot.add_cog(AdminCog(bot))
