# Privacy and Data Handling

## What We Store
- Discord identifiers: user IDs, guild IDs, role mappings, channel IDs, and limited audit context for administrative actions.
- Verification data: RSI handle, verification state flags, optional organization metadata, and timestamped status changes.
- Voice preferences: per-channel settings, permissions, PTT/priority/soundboard flags, selectable roles, and cooldown timestamps for join-to-create flows.
- Operational logs: administrative action log entries, integrity checks, and export activity needed for support and abuse investigations.

## How Deletion Requests Are Processed
- Users open a Discord support ticket requesting deletion.
- Staff verify ownership, then remove verification records, voice channel preferences, and related audit entries using the existing admin tooling.
- Direct messages are not stored; we never archive message content.

## Retention
- Operational logs and audit entries are retained for a short operational window (typically 30–90 days, default ~60 days) unless a longer period is required for an active investigation.
- Retention helpers (manual and schedulable) exist to purge audit/log tables; staff can trigger cleanup after tickets close.
- The schema is current—there are no legacy migrations or backwards-compatibility tables pending cleanup.

## Data Minimization
- We do not store message content or tokens.
- Data is kept only to operate verification, role management, and voice automation features.
- Retention helpers are used conservatively to avoid unexpected production changes.
