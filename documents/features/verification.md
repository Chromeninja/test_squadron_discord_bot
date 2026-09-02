# Verification

## Purpose

Verification checks a member's RSI identity and organization membership, then
applies the configured Discord roles and nickname rules.

## User flow

1. A member starts verification from the persistent verification message.
2. The bot validates the submitted token and RSI response.
3. Successful verification stores the member's RSI and organization details.
4. Roles and nickname are updated when Discord permissions allow it.
5. Failures are rate-limited, logged, and presented without exposing secrets.

## Code ownership

- Discord commands/UI: `cogs/verification/`, `helpers/views_verification.py`,
  and `helpers/verification_messages.py`.
- RSI parsing and circuit breaking: `verification/`.
- Orchestration and scheduling: `services/verification_*`.
- Authoritative persistence: `backend/db/repository/verification.py` and
  `backend/api/internal/verification.py`.
- Bot HTTP boundary: `connectors/verification.py`.

Administrative checks support one member, many members, a voice channel, or
all active voice channels. `check` reports status; `recheck` forces a fresh
verification and may change roles or nicknames.

## Important constraints

Keep RSI traffic mocked in tests, preserve the circuit breaker, enforce guild
scope, and never log tokens or private RSI payloads. The bot needs Manage Roles,
Change Nickname, and Manage Nicknames permissions for the complete flow.
