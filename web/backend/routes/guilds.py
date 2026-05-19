"""Guild-specific management endpoints."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from core.dependencies import (
    InternalAPIClient,
    get_config_loader,
    get_db,
    get_internal_api_client,
    require_bot_admin,
    require_fresh_guild_access,
    require_is_bot_owner,
    require_moderator,
    require_staff,
    translate_internal_api_error,
)
from core.guild_settings import (
    AFFILIATE_ROLE_KEY,
    BOT_ADMINS_KEY,
    BOT_SPAM_CHANNEL_KEY,
    BOT_VERIFIED_ROLE_KEY,
    DELEGATION_POLICIES_KEY,
    DISCORD_MANAGERS_KEY,
    EVENT_COORDINATORS_KEY,
    EVENTS_DEFAULT_ANNOUNCEMENT_CHANNEL_KEY,
    EVENTS_DEFAULT_NATIVE_SYNC_KEY,
    EVENTS_DEFAULT_VOICE_CHANNEL_KEY,
    EVENTS_ENABLED_KEY,
    LEADERSHIP_ANNOUNCEMENT_CHANNEL_KEY,
    MAIN_ROLE_KEY,
    METRICS_EXCLUDED_CHANNEL_IDS_KEY,
    MODERATORS_KEY,
    NONMEMBER_ROLE_KEY,
    ORGANIZATION_LOGO_URL_KEY,
    ORGANIZATION_NAME_KEY,
    ORGANIZATION_SID_KEY,
    PUBLIC_ANNOUNCEMENT_CHANNEL_KEY,
    SELECTABLE_ROLES_KEY,
    SETTINGS_VERSION_NEW_MEMBER_ROLE_SOURCE,
    STAFF_KEY,
    VERIFICATION_CHANNEL_KEY,
    LogoValidationError,
    _normalize_delegation_policies,
    get_bot_channel_settings,
    get_bot_role_settings,
    get_event_module_settings,
    get_metrics_settings,
    get_new_member_role_settings,
    get_organization_settings,
    get_voice_selectable_roles,
    set_bot_channel_settings,
    set_bot_role_settings,
    set_event_module_settings,
    set_metrics_settings,
    set_new_member_role_settings,
    set_organization_settings,
    set_voice_selectable_roles,
    validate_logo_url,
)
from core.schemas import (
    BotChannelSettings,
    BotChannelSettingsResponse,
    BotRoleSettings,
    EventModuleSettings,
    GuildConfigData,
    GuildConfigResponse,
    GuildConfigUpdateRequest,
    GuildInfo,
    GuildInfoResponse,
    MetricsSettings,
    NewMemberRoleSettings,
    OrganizationSettings,
    ReadOnlyYamlConfig,
    RoleDelegationPolicy,
    UserProfile,
    VoiceSelectableRoles,
)
from core.validation import (
    ensure_guild_match,
)
from fastapi import APIRouter, Depends, HTTPException

if TYPE_CHECKING:
    from config.config_loader import ConfigLoader

router = APIRouter(prefix="/api/guilds", tags=["guilds"])
logger = logging.getLogger(__name__)


@router.get(
    "/{guild_id}/settings/bot-roles",
    response_model=BotRoleSettings,
    dependencies=[Depends(require_fresh_guild_access)],
)
async def get_bot_roles_settings(
    guild_id: int,
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_staff()),
):
    """Fetch stored bot role assignments for a guild."""
    ensure_guild_match(guild_id, current_user)
    settings = await get_bot_role_settings(db, guild_id)
    policies = [
        RoleDelegationPolicy(**policy)
        for policy in settings.get("delegation_policies", [])
    ]
    return BotRoleSettings(
        bot_admins=settings.get("bot_admins", []),  # type: ignore[arg-type]
        discord_managers=settings.get("discord_managers", []),  # type: ignore[arg-type]
        moderators=settings.get("moderators", []),  # type: ignore[arg-type]
        event_coordinators=settings.get("event_coordinators", []),  # type: ignore[arg-type]
        staff=settings.get("staff", []),  # type: ignore[arg-type]
        bot_verified_role=settings.get("bot_verified_role", []),  # type: ignore[arg-type]
        main_role=settings.get("main_role", []),  # type: ignore[arg-type]
        affiliate_role=settings.get("affiliate_role", []),  # type: ignore[arg-type]
        nonmember_role=settings.get("nonmember_role", []),  # type: ignore[arg-type]
        delegation_policies=policies,
    )


@router.put(
    "/{guild_id}/settings/bot-roles",
    response_model=BotRoleSettings,
    dependencies=[Depends(require_fresh_guild_access)],
)
async def update_bot_roles_settings(
    guild_id: int,
    payload: BotRoleSettings,
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_bot_admin()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """Persist admin, moderator, and member category role assignments for a guild."""
    ensure_guild_match(guild_id, current_user)
    try:
        normalized_policies = _normalize_delegation_policies(
            payload.delegation_policies, strict=True
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await set_bot_role_settings(
        db,
        guild_id,
        payload.bot_admins,
        payload.discord_managers,
        payload.moderators,
        payload.event_coordinators,
        payload.staff,
        payload.bot_verified_role,
        payload.main_role,
        payload.affiliate_role,
        payload.nonmember_role,
        normalized_policies,
    )
    updated = await get_bot_role_settings(db, guild_id)

    # Fire-and-forget notification to bot; warn on failure but don't block response
    try:
        await internal_api.notify_guild_settings_refresh(guild_id, source="bot_roles")
    except Exception as exc:  # pragma: no cover - network errors
        logger.warning(
            "Failed to notify bot about guild %s role change: %s", guild_id, exc
        )

    updated_policies = [
        RoleDelegationPolicy(**policy)
        for policy in updated.get("delegation_policies", [])
    ]
    return BotRoleSettings(
        bot_admins=updated.get("bot_admins", []),  # type: ignore[arg-type]
        discord_managers=updated.get("discord_managers", []),  # type: ignore[arg-type]
        moderators=updated.get("moderators", []),  # type: ignore[arg-type]
        event_coordinators=updated.get("event_coordinators", []),  # type: ignore[arg-type]
        staff=updated.get("staff", []),  # type: ignore[arg-type]
        bot_verified_role=updated.get("bot_verified_role", []),  # type: ignore[arg-type]
        main_role=updated.get("main_role", []),  # type: ignore[arg-type]
        affiliate_role=updated.get("affiliate_role", []),  # type: ignore[arg-type]
        nonmember_role=updated.get("nonmember_role", []),  # type: ignore[arg-type]
        delegation_policies=updated_policies,
    )


@router.get(
    "/{guild_id}/settings/bot-channels",
    response_model=BotChannelSettings,
    dependencies=[Depends(require_fresh_guild_access)],
)
async def get_bot_channels_settings(
    guild_id: int,
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_moderator()),
):
    """Fetch stored bot channel assignments for a guild."""
    ensure_guild_match(guild_id, current_user)
    settings = await get_bot_channel_settings(db, guild_id)
    return BotChannelSettings(**settings)


@router.put(
    "/{guild_id}/settings/bot-channels",
    response_model=BotChannelSettingsResponse,
    dependencies=[Depends(require_fresh_guild_access)],
)
async def update_bot_channels_settings(
    guild_id: int,
    payload: BotChannelSettings,
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_moderator()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """Persist bot channel assignments for a guild."""
    ensure_guild_match(guild_id, current_user)
    current_channels = (await get_bot_channel_settings(db, guild_id)) or {}
    await set_bot_channel_settings(
        db,
        guild_id,
        payload.verification_channel_id,
        payload.bot_spam_channel_id,
        payload.public_announcement_channel_id,
        payload.leadership_announcement_channel_id,
    )
    updated = await get_bot_channel_settings(db, guild_id)

    # Track verification message update status
    verification_message_updated: bool | None = None

    # Push refresh and resend verification message if channel changed
    try:
        await _notify_refresh(internal_api, guild_id, source="bot_channels")
        if (
            payload.verification_channel_id
            and payload.verification_channel_id
            != current_channels.get("verification_channel_id")
        ):
            await internal_api.resend_verification_message(guild_id)
            verification_message_updated = True
    except Exception as exc:
        # Log and track failure
        if (
            payload.verification_channel_id
            and payload.verification_channel_id
            != current_channels.get("verification_channel_id")
        ):
            logger.warning(
                "Failed to resend verification message for guild %s after channel update: %s",
                guild_id,
                exc,
            )
            verification_message_updated = False

    return BotChannelSettingsResponse(
        **updated,
        verification_message_updated=verification_message_updated,
    )


@router.get(
    "/{guild_id}/settings/voice/selectable-roles",
    response_model=VoiceSelectableRoles,
    dependencies=[Depends(require_fresh_guild_access)],
)
async def get_voice_selectable_roles_endpoint(
    guild_id: int,
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_staff()),
):
    """Return selectable roles that voice automations can target for a guild."""
    ensure_guild_match(guild_id, current_user)
    role_ids = await get_voice_selectable_roles(db, guild_id)
    return VoiceSelectableRoles(selectable_roles=role_ids)


@router.put(
    "/{guild_id}/settings/voice/selectable-roles",
    response_model=VoiceSelectableRoles,
    dependencies=[Depends(require_fresh_guild_access)],
)
async def update_voice_selectable_roles_settings(
    guild_id: int,
    payload: VoiceSelectableRoles,
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_moderator()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """Persist selectable voice role IDs for a guild."""
    ensure_guild_match(guild_id, current_user)
    await set_voice_selectable_roles(db, guild_id, payload.selectable_roles)
    updated = await get_voice_selectable_roles(db, guild_id)
    await _notify_refresh(internal_api, guild_id, source="voice_selectable_roles")
    return VoiceSelectableRoles(selectable_roles=updated)


# Guild info (for header)
@router.get(
    "/{guild_id}/info",
    response_model=GuildInfoResponse,
    dependencies=[Depends(require_fresh_guild_access)],
)
async def get_guild_info(
    guild_id: int,
    current_user: UserProfile = Depends(require_staff()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """Return basic guild identity (name, icon) for UI header."""
    ensure_guild_match(guild_id, current_user)

    try:
        guilds = await internal_api.get_guilds()
    except Exception as exc:  # pragma: no cover - transport errors
        raise translate_internal_api_error(exc, "Failed to fetch guild info") from exc

    gid_str = str(guild_id)
    match = None
    for g in guilds:
        if str(g.get("guild_id")) == gid_str:
            match = g
            break

    if not match:
        raise HTTPException(status_code=404, detail="Guild not found")

    info = GuildInfo(
        guild_id=gid_str,
        guild_name=match.get("guild_name", "Unnamed Guild"),
        icon_url=match.get("icon_url"),
    )
    return GuildInfoResponse(guild=info)


def _read_only_yaml_snapshot(config_loader: ConfigLoader) -> dict:
    """Return a small subset of global YAML config for read-only display."""
    cfg = config_loader.load_config()

    return {
        "rsi": cfg.get("rsi"),
        "voice": cfg.get("voice"),
        "voice_debug_logging_enabled": cfg.get("voice_debug_logging_enabled"),
    }


async def _notify_refresh(
    internal_api: InternalAPIClient, guild_id: int, source: str | None = None
) -> None:
    """Best-effort push refresh to the bot after config changes."""
    try:
        await internal_api.notify_guild_settings_refresh(guild_id, source=source)
    except Exception as exc:  # pragma: no cover - transport errors
        logger.warning(
            "Failed to notify bot about guild %s config change: %s", guild_id, exc
        )


@router.get(
    "/{guild_id}/config",
    response_model=GuildConfigResponse,
    dependencies=[Depends(require_fresh_guild_access)],
)
async def get_guild_config(
    guild_id: int,
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_staff()),
    config_loader: ConfigLoader = Depends(get_config_loader),
):
    """Return merged guild configuration (DB-backed + read-only YAML subset)."""
    ensure_guild_match(guild_id, current_user)

    roles = await get_bot_role_settings(db, guild_id)
    channels = await get_bot_channel_settings(db, guild_id)
    voice_roles = await get_voice_selectable_roles(db, guild_id)
    metrics = await get_metrics_settings(db, guild_id)
    org = await get_organization_settings(db, guild_id)
    events = await get_event_module_settings(db, guild_id)

    ro = _read_only_yaml_snapshot(config_loader)

    hydrated_policies = [
        RoleDelegationPolicy(**policy)
        for policy in roles.get("delegation_policies", [])
    ]

    data = GuildConfigData(
        roles=BotRoleSettings(
            bot_admins=roles.get("bot_admins", []),  # type: ignore[arg-type]
            discord_managers=roles.get("discord_managers", []),  # type: ignore[arg-type]
            moderators=roles.get("moderators", []),  # type: ignore[arg-type]
            event_coordinators=roles.get("event_coordinators", []),  # type: ignore[arg-type]
            staff=roles.get("staff", []),  # type: ignore[arg-type]
            bot_verified_role=roles.get("bot_verified_role", []),  # type: ignore[arg-type]
            main_role=roles.get("main_role", []),  # type: ignore[arg-type]
            affiliate_role=roles.get("affiliate_role", []),  # type: ignore[arg-type]
            nonmember_role=roles.get("nonmember_role", []),  # type: ignore[arg-type]
            delegation_policies=hydrated_policies,
        ),
        channels=BotChannelSettings(**channels),
        voice=VoiceSelectableRoles(selectable_roles=voice_roles),
        metrics=MetricsSettings(**metrics),
        organization=OrganizationSettings(**org),
        events=EventModuleSettings(**events),
        read_only=ReadOnlyYamlConfig(**ro),
    )

    return GuildConfigResponse(data=data)


async def _audit_change(
    db, guild_id: int, key: str, old_value, new_value, actor_user_id: int | None
):
    """Insert an audit record for a changed key."""
    await db.execute(
        """
        INSERT INTO guild_settings_audit (guild_id, key, old_value, new_value, changed_by_user_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            guild_id,
            key,
            json.dumps(old_value),
            json.dumps(new_value),
            int(actor_user_id) if actor_user_id is not None else None,
        ),
    )


@router.patch(
    "/{guild_id}/config",
    response_model=GuildConfigResponse,
    dependencies=[Depends(require_fresh_guild_access)],
)
async def patch_guild_config(
    guild_id: int,
    payload: GuildConfigUpdateRequest,
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_bot_admin()),
    config_loader: ConfigLoader = Depends(get_config_loader),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """Update DB-backed guild settings. YAML-only fields remain read-only."""
    ensure_guild_match(guild_id, current_user)

    try:
        actor_user_id = int(current_user.user_id)
    except (TypeError, ValueError):
        actor_user_id = None

    # Fetch current values for auditing
    current_roles = await get_bot_role_settings(db, guild_id)
    current_channels = await get_bot_channel_settings(db, guild_id)
    current_voice = await get_voice_selectable_roles(db, guild_id)
    current_metrics = await get_metrics_settings(db, guild_id)
    current_org = await get_organization_settings(db, guild_id)
    current_events = await get_event_module_settings(db, guild_id)

    # Track whether verification channel changed for resend trigger
    verification_channel_changed = False

    # Apply updates if provided
    if payload.roles is not None:
        try:
            normalized_policies = _normalize_delegation_policies(
                payload.roles.delegation_policies, strict=True
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        await set_bot_role_settings(
            db,
            guild_id,
            payload.roles.bot_admins,
            payload.roles.discord_managers,
            payload.roles.moderators,
            payload.roles.event_coordinators,
            payload.roles.staff,
            payload.roles.bot_verified_role,
            payload.roles.main_role,
            payload.roles.affiliate_role,
            payload.roles.nonmember_role,
            normalized_policies,
        )

        # Audit each role list if changed
        if current_roles.get("bot_admins") != payload.roles.bot_admins:
            await _audit_change(
                db,
                guild_id,
                BOT_ADMINS_KEY,
                current_roles.get("bot_admins"),
                payload.roles.bot_admins,
                actor_user_id,
            )
        if current_roles.get("discord_managers") != payload.roles.discord_managers:
            await _audit_change(
                db,
                guild_id,
                DISCORD_MANAGERS_KEY,
                current_roles.get("discord_managers"),
                payload.roles.discord_managers,
                actor_user_id,
            )
        if current_roles.get("moderators") != payload.roles.moderators:
            await _audit_change(
                db,
                guild_id,
                MODERATORS_KEY,
                current_roles.get("moderators"),
                payload.roles.moderators,
                actor_user_id,
            )
        if current_roles.get("event_coordinators") != payload.roles.event_coordinators:
            await _audit_change(
                db,
                guild_id,
                EVENT_COORDINATORS_KEY,
                current_roles.get("event_coordinators"),
                payload.roles.event_coordinators,
                actor_user_id,
            )
        if current_roles.get("staff") != payload.roles.staff:
            await _audit_change(
                db,
                guild_id,
                STAFF_KEY,
                current_roles.get("staff"),
                payload.roles.staff,
                actor_user_id,
            )
        if current_roles.get("bot_verified_role") != payload.roles.bot_verified_role:
            await _audit_change(
                db,
                guild_id,
                BOT_VERIFIED_ROLE_KEY,
                current_roles.get("bot_verified_role"),
                payload.roles.bot_verified_role,
                actor_user_id,
            )
        if current_roles.get("main_role") != payload.roles.main_role:
            await _audit_change(
                db,
                guild_id,
                MAIN_ROLE_KEY,
                current_roles.get("main_role"),
                payload.roles.main_role,
                actor_user_id,
            )
        if current_roles.get("affiliate_role") != payload.roles.affiliate_role:
            await _audit_change(
                db,
                guild_id,
                AFFILIATE_ROLE_KEY,
                current_roles.get("affiliate_role"),
                payload.roles.affiliate_role,
                actor_user_id,
            )
        if current_roles.get("nonmember_role") != payload.roles.nonmember_role:
            await _audit_change(
                db,
                guild_id,
                NONMEMBER_ROLE_KEY,
                current_roles.get("nonmember_role"),
                payload.roles.nonmember_role,
                actor_user_id,
            )
        if current_roles.get("delegation_policies") != normalized_policies:
            await _audit_change(
                db,
                guild_id,
                DELEGATION_POLICIES_KEY,
                current_roles.get("delegation_policies"),
                normalized_policies,
                actor_user_id,
            )

    if payload.channels is not None:
        await set_bot_channel_settings(
            db,
            guild_id,
            payload.channels.verification_channel_id,
            payload.channels.bot_spam_channel_id,
            payload.channels.public_announcement_channel_id,
            payload.channels.leadership_announcement_channel_id,
        )

        if (
            current_channels.get("verification_channel_id")
            != payload.channels.verification_channel_id
            and payload.channels.verification_channel_id is not None
        ):
            verification_channel_changed = True

        if (
            current_channels.get("verification_channel_id")
            != payload.channels.verification_channel_id
        ):
            await _audit_change(
                db,
                guild_id,
                VERIFICATION_CHANNEL_KEY,
                current_channels.get("verification_channel_id"),
                payload.channels.verification_channel_id,
                actor_user_id,
            )
        if (
            current_channels.get("bot_spam_channel_id")
            != payload.channels.bot_spam_channel_id
        ):
            await _audit_change(
                db,
                guild_id,
                BOT_SPAM_CHANNEL_KEY,
                current_channels.get("bot_spam_channel_id"),
                payload.channels.bot_spam_channel_id,
                actor_user_id,
            )
        if (
            current_channels.get("public_announcement_channel_id")
            != payload.channels.public_announcement_channel_id
        ):
            await _audit_change(
                db,
                guild_id,
                PUBLIC_ANNOUNCEMENT_CHANNEL_KEY,
                current_channels.get("public_announcement_channel_id"),
                payload.channels.public_announcement_channel_id,
                actor_user_id,
            )
        if (
            current_channels.get("leadership_announcement_channel_id")
            != payload.channels.leadership_announcement_channel_id
        ):
            await _audit_change(
                db,
                guild_id,
                LEADERSHIP_ANNOUNCEMENT_CHANNEL_KEY,
                current_channels.get("leadership_announcement_channel_id"),
                payload.channels.leadership_announcement_channel_id,
                actor_user_id,
            )

    if payload.voice is not None:
        await set_voice_selectable_roles(db, guild_id, payload.voice.selectable_roles)
        if current_voice != payload.voice.selectable_roles:
            await _audit_change(
                db,
                guild_id,
                SELECTABLE_ROLES_KEY,
                current_voice,
                payload.voice.selectable_roles,
                actor_user_id,
            )

    if payload.metrics is not None:
        await set_metrics_settings(
            db,
            guild_id,
            payload.metrics.excluded_channel_ids,
            tracked_games_mode=payload.metrics.tracked_games_mode,
            tracked_games=payload.metrics.tracked_games,
            min_voice_minutes=payload.metrics.min_voice_minutes,
            min_game_minutes=payload.metrics.min_game_minutes,
            min_messages=payload.metrics.min_messages,
        )
        updated_metrics = await get_metrics_settings(db, guild_id)
        if current_metrics.get("excluded_channel_ids") != updated_metrics.get(
            "excluded_channel_ids"
        ):
            await _audit_change(
                db,
                guild_id,
                METRICS_EXCLUDED_CHANNEL_IDS_KEY,
                current_metrics.get("excluded_channel_ids"),
                updated_metrics.get("excluded_channel_ids"),
                actor_user_id,
            )

    logo_changed = False
    if payload.organization is not None:
        # Validate logo URL if provided
        validated_logo_url = None
        if payload.organization.organization_logo_url:
            try:
                validated_logo_url = await validate_logo_url(
                    payload.organization.organization_logo_url
                )
            except LogoValidationError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        logo_changed = current_org.get("organization_logo_url") != validated_logo_url

        await set_organization_settings(
            db,
            guild_id,
            payload.organization.organization_sid,
            payload.organization.organization_name,
            validated_logo_url,
        )

        if current_org.get("organization_sid") != payload.organization.organization_sid:
            await _audit_change(
                db,
                guild_id,
                ORGANIZATION_SID_KEY,
                current_org.get("organization_sid"),
                payload.organization.organization_sid,
                actor_user_id,
            )
        if (
            current_org.get("organization_name")
            != payload.organization.organization_name
        ):
            await _audit_change(
                db,
                guild_id,
                ORGANIZATION_NAME_KEY,
                current_org.get("organization_name"),
                payload.organization.organization_name,
                actor_user_id,
            )
        if logo_changed:
            await _audit_change(
                db,
                guild_id,
                ORGANIZATION_LOGO_URL_KEY,
                current_org.get("organization_logo_url"),
                validated_logo_url,
                actor_user_id,
            )

    if payload.events is not None:
        await set_event_module_settings(
            db,
            guild_id,
            enabled=payload.events.enabled,
            default_native_sync=payload.events.default_native_sync,
            default_announcement_channel_id=payload.events.default_announcement_channel_id,
            default_voice_channel_id=payload.events.default_voice_channel_id,
        )

        if current_events.get("enabled") != payload.events.enabled:
            await _audit_change(
                db,
                guild_id,
                EVENTS_ENABLED_KEY,
                current_events.get("enabled"),
                payload.events.enabled,
                actor_user_id,
            )
        if (
            current_events.get("default_native_sync")
            != payload.events.default_native_sync
        ):
            await _audit_change(
                db,
                guild_id,
                EVENTS_DEFAULT_NATIVE_SYNC_KEY,
                current_events.get("default_native_sync"),
                payload.events.default_native_sync,
                actor_user_id,
            )
        if (
            current_events.get("default_announcement_channel_id")
            != payload.events.default_announcement_channel_id
        ):
            await _audit_change(
                db,
                guild_id,
                EVENTS_DEFAULT_ANNOUNCEMENT_CHANNEL_KEY,
                current_events.get("default_announcement_channel_id"),
                payload.events.default_announcement_channel_id,
                actor_user_id,
            )
        if (
            current_events.get("default_voice_channel_id")
            != payload.events.default_voice_channel_id
        ):
            await _audit_change(
                db,
                guild_id,
                EVENTS_DEFAULT_VOICE_CHANNEL_KEY,
                current_events.get("default_voice_channel_id"),
                payload.events.default_voice_channel_id,
                actor_user_id,
            )

    # Commit any pending audit inserts
    await db.commit()

    # Best-effort push refresh to bot and resend verification message if needed
    await _notify_refresh(internal_api, guild_id, source="guild_config_patch")
    if verification_channel_changed or logo_changed:
        try:
            await internal_api.resend_verification_message(guild_id)
        except Exception as exc:  # pragma: no cover - transport errors
            logger.warning(
                "Failed to resend verification message for guild %s: %s",
                guild_id,
                exc,
            )

    # Return updated merged view
    return await get_guild_config(
        guild_id, db=db, current_user=current_user, config_loader=config_loader
    )


@router.get(
    "/{guild_id}/settings/new-member-role",
    response_model=NewMemberRoleSettings,
    dependencies=[Depends(require_fresh_guild_access)],
)
async def get_new_member_role_settings_endpoint(
    guild_id: int,
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_staff()),
):
    """Fetch new-member role module settings for a guild."""
    ensure_guild_match(guild_id, current_user)
    settings = await get_new_member_role_settings(db, guild_id)
    return NewMemberRoleSettings(**settings)


@router.put(
    "/{guild_id}/settings/new-member-role",
    response_model=NewMemberRoleSettings,
    dependencies=[Depends(require_fresh_guild_access)],
)
async def update_new_member_role_settings_endpoint(
    guild_id: int,
    payload: NewMemberRoleSettings,
    db=Depends(get_db),
    current_user: UserProfile = Depends(require_bot_admin()),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """Persist new-member role module settings for a guild."""
    ensure_guild_match(guild_id, current_user)
    await set_new_member_role_settings(
        db,
        guild_id,
        enabled=payload.enabled,
        role_id=payload.role_id,
        duration_days=payload.duration_days,
        max_server_age_days=payload.max_server_age_days,
    )

    # Fire-and-forget notification to bot
    try:
        await internal_api.notify_guild_settings_refresh(
            guild_id, source=SETTINGS_VERSION_NEW_MEMBER_ROLE_SOURCE
        )
    except Exception as exc:  # pragma: no cover - network errors
        logger.warning(
            "Failed to notify bot about new-member-role settings change (%s)",
            type(exc).__name__,
        )

    updated = await get_new_member_role_settings(db, guild_id)
    return NewMemberRoleSettings(**updated)


@router.post("/{guild_id}/leave")
async def leave_guild(
    guild_id: int,
    current_user: UserProfile = Depends(require_is_bot_owner),
    internal_api: InternalAPIClient = Depends(get_internal_api_client),
):
    """
    Make the bot leave a guild. Bot owner only.

    This is a privileged operation that removes the bot from the specified guild.
    Only the bot owner can perform this action. Does not require active guild selection.
    """
    import logging

    logger = logging.getLogger(__name__)

    # Note: require_is_bot_owner validates is_bot_owner in session
    # No need to check active_guild_id match - bot owner can leave ANY guild

    try:
        result = await internal_api.leave_guild(guild_id)
        logger.info(
            "Bot owner %s triggered leave for guild %s (%s)",
            current_user.user_id,
            guild_id,
            result.get("guild_name", "unknown"),
        )
        return {
            "success": True,
            "guild_id": guild_id,
            "guild_name": result.get("guild_name"),
        }
    except Exception as exc:
        raise translate_internal_api_error(exc, "Failed to leave guild") from exc
