# Web Dashboard

## Purpose

The dashboard provides authorized staff with guild configuration, verification
lookup, voice management, ticket/event administration, logs, statistics, and
activity metrics.

## Request flow

1. The React frontend authenticates through Discord OAuth2.
2. The dashboard backend creates and validates the session cookie.
3. Every protected request resolves the guild and checks the configured role
   hierarchy.
4. Dashboard routes use the existing backend/connector boundaries and return
   validated response models.

## Code ownership

- Frontend: `web/frontend/src/`.
- OAuth/session and route handlers: `web/backend/core/` and
  `web/backend/routes/`.
- Authoritative data/API: `backend/`.

Bot-only operations that require a live Discord connection must remain behind
the existing internal API/gateway boundary. Test unauthenticated,
unauthorized, expired-session, guild-isolation, and valid-access paths.
