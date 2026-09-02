# Voice Channel Management

## Purpose

The bot manages temporary user voice channels. Users control settings through
Discord UI components while the bot retains channel-management authority.

## User flow

1. A member joins a configured join-to-create channel.
2. The bot creates or reuses a personal voice channel and records ownership.
3. The owner opens the settings UI to manage name, limit, visibility, and
   member permissions.
4. Owners can list settings, transfer ownership, or claim an abandoned channel.
5. Empty temporary channels are reconciled and cleaned up safely.

## Code ownership

- Commands and gateway events: `cogs/voice/`.
- Interactive views and permissions: `helpers/views_voice.py`,
  `helpers/voice_permissions.py`, and `helpers/voice_settings.py`.
- Service orchestration: `services/voice_*` and `services/voice_service.py`.
- Persistence: `backend/db/repository/voice.py` and `backend/api/internal/voice.py`.
- Bot HTTP boundary: `connectors/voice.py`.

Administrative reset supports a single user or all voice records and requires
confirmation for broad operations. Test missing guild/member/channel state and
Discord API failures without live Discord calls.

The bot needs Manage Channels, Connect, Move Members, and appropriate category
permissions. Do not grant Administrator solely for this feature.
