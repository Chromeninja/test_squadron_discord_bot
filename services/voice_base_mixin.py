"""
VoiceServiceBase — shared type declarations for all VoiceService mixins.

All voice mixins inherit from this class.  The ``if TYPE_CHECKING:`` block
means **zero runtime impact** (the block is never executed), so no MRO
shadowing of ``BaseService`` methods occurs.  Pylance / pyright see every
attribute and method stub and can type-check each mixin in isolation.

Do not import directly; import ``VoiceService`` from
``services.voice_service``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    import discord

    from services.config_service import ConfigService
    from utils.types import VoiceChannelInfo


class VoiceServiceBase:
    """
    Shared attribute declarations for all VoiceService mixins.

    This class contains *only* type annotations (inside ``if TYPE_CHECKING``).
    At runtime the block is skipped entirely, so no class attributes are
    created and the MRO of the concrete ``VoiceService`` class is unaffected.

    AI Notes:
        Every attribute and method declared here corresponds to something
        that ``VoiceService.__init__`` / ``BaseService.__init__`` or one of
        the sibling mixins provides at runtime via Python's MRO.
    """

    if TYPE_CHECKING:
        # ------------------------------------------------------------------
        # Instance attributes — set by BaseService.__init__
        # ------------------------------------------------------------------
        logger: logging.Logger
        _initialized: bool

        # ------------------------------------------------------------------
        # Instance attributes — set by VoiceService.__init__
        # ------------------------------------------------------------------
        config_service: ConfigService
        bot: discord.Client | None
        test_mode: bool
        debug_logging_enabled: bool
        managed_voice_channels: set[int]
        _voice_channel_members: dict[int, set[int]]
        _creation_unmark_delay: float
        _users_creating_channels: set[tuple[int, int]]
        _background_tasks: set[asyncio.Task[Any]]
        _creation_locks: dict[tuple[str, int, int], asyncio.Lock]
        _lock_last_used: dict[tuple[str, int, int], float]
        _locks_lock: asyncio.Lock

        # ------------------------------------------------------------------
        # ClassVar constants — declared on VoiceService
        # ------------------------------------------------------------------
        ORPHAN_OWNER_ID: ClassVar[int]
        CHANNEL_CREATION_TIMEOUT_SECONDS: ClassVar[float]
        INACTIVE_CHANNEL_PURGE_DAYS: ClassVar[int]
        BOT_CREATION_OVERWRITE_PERMISSIONS: ClassVar[dict[str, bool]]
        OWNER_CREATION_OVERWRITE_PERMISSIONS: ClassVar[dict[str, bool]]

        # ------------------------------------------------------------------
        # Methods from BaseService (called by some mixins)
        # ------------------------------------------------------------------
        def _ensure_initialized(self) -> None: ...

        async def health_check(self) -> dict[str, Any]: ...

        # ------------------------------------------------------------------
        # Methods defined on VoiceService (called cross-mixin)
        # ------------------------------------------------------------------
        def _spawn_background_task(
            self, coro: Coroutine[Any, Any, Any], *, name: str
        ) -> asyncio.Task[Any]: ...

        def _mark_user_creating(self, guild_id: int, user_id: int) -> None: ...

        def _is_user_creating(self, guild_id: int, user_id: int) -> bool: ...

        async def _delayed_unmark_user_creating(
            self,
            guild_id: int,
            user_id: int,
            delay: float | None = None,
        ) -> None: ...

        async def _get_creation_lock(
            self, guild_id: int, user_id: int
        ) -> asyncio.Lock: ...

        async def _cleanup_stale_locks(
            self, max_age_seconds: int | None = None
        ) -> None: ...

        def _get_member_count(
            self,
            channel_or_id: discord.VoiceChannel
            | discord.StageChannel
            | int
            | None,
        ) -> int: ...

        def _classify_old_channel(self, member_count: int) -> str: ...

        @staticmethod
        def _sanitize_overwrite(
            overwrite: discord.PermissionOverwrite,
            bot_perms: discord.Permissions,
        ) -> discord.PermissionOverwrite: ...

        async def _delete_channel_safe(
            self,
            channel_or_id: discord.VoiceChannel | discord.StageChannel | int,
            reason: str = "Channel cleanup",
            *,
            cleanup_tracking: bool = True,
        ) -> bool: ...

        async def _handle_orphan_or_delete(
            self,
            *,
            db: Any,
            action: str,
            user_id: int,
            old_channel_id: int,
            old_channel: discord.VoiceChannel | discord.StageChannel | None,
        ) -> discord.VoiceChannel | None: ...

        # ------------------------------------------------------------------
        # Methods from VoiceStateMixin (called by other mixins)
        # ------------------------------------------------------------------
        async def _cleanup_empty_channel(
            self, channel_or_id: discord.VoiceChannel | int
        ) -> None: ...

        async def _is_managed_channel(self, channel_id: int) -> bool: ...

        async def _is_join_to_create_channel(
            self, guild_id: int, channel_id: int
        ) -> bool: ...

        async def _notify_bot_spam_channel(
            self, guild: discord.Guild, message: str
        ) -> None: ...

        async def _send_settings_message_to_vc(
            self,
            voice_channel: discord.VoiceChannel,
            member: discord.Member,
            view: discord.ui.View,
        ) -> None: ...

        # ------------------------------------------------------------------
        # Methods from VoiceCreateMixin (called by other mixins)
        # ------------------------------------------------------------------
        async def _create_user_channel(
            self,
            guild: discord.Guild,
            jtc_channel: discord.VoiceChannel,
            member: discord.Member,
        ) -> discord.VoiceChannel | None: ...

        async def _schedule_channel_cleanup(
            self, channel_id: int
        ) -> asyncio.Task[Any]: ...

        # ------------------------------------------------------------------
        # Methods from VoiceChannelMixin (called by other mixins)
        # ------------------------------------------------------------------
        async def can_create_voice_channel(
            self,
            guild_id: int,
            jtc_channel_id: int,
            user_id: int,
            *,
            bypass_cooldown: bool = False,
        ) -> tuple[bool, str | None]: ...

        async def cleanup_by_channel_id(self, voice_channel_id: int) -> None: ...

        async def _update_cooldown(
            self, guild_id: int, jtc_channel_id: int, user_id: int
        ) -> None: ...

        async def _purge_inactive_voice_channels(
            self, older_than_seconds: int | None = None
        ) -> int: ...

        # ------------------------------------------------------------------
        # Methods from VoiceJtcMixin (called by other mixins)
        # ------------------------------------------------------------------
        async def _get_guild_jtc_channels(self, guild_id: int) -> list[int]: ...

        async def _load_channel_settings(
            self, guild_id: int, jtc_channel_id: int, user_id: int
        ) -> dict[str, Any] | None: ...

        # ------------------------------------------------------------------
        # Methods from VoiceSetupMixin (called by other mixins)
        # ------------------------------------------------------------------
        async def _validate_jtc_permissions(
            self, category: discord.CategoryChannel
        ) -> tuple[bool, str | None]: ...

        async def remove_jtc_channel_from_config(
            self,
            guild_id: int,
            channel_id: int,
            cleanup_managed: bool = True,
        ) -> dict[str, Any]: ...

        # ------------------------------------------------------------------
        # Methods from VoiceSettingsMixin (called by other mixins)
        # ------------------------------------------------------------------
        async def get_user_voice_channel_info(
            self, guild_id: int, user_id: int
        ) -> VoiceChannelInfo | None: ...
