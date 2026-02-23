# Privacy and Data Handling

This document explains what personal data TEST Clanker processes, why it is processed, and how user rights requests are handled.

## Controller and Contact
- Controller: TEST Squadron (community operators of this bot)
- Contact: Chromeninja@test.gg
- Support channel: Open a Discord support ticket in the TEST Squadron server

## Legal Basis (GDPR)
- Primary legal basis: **Legitimate Interests** (GDPR Article 6(1)(f)) to operate community verification, moderation, safety, and automation features.
- We apply data minimization and retention limits consistent with GDPR Article 5.

## What We Store
- Discord identifiers: user IDs, guild IDs, role mappings, channel IDs, and limited audit context for administrative actions.
- Verification data: RSI handle, verification state flags, optional organization metadata, and timestamped status changes.
- Voice preferences: per-channel settings, permissions, PTT/priority/soundboard flags, selectable roles, and cooldown timestamps for join-to-create flows.
- Metrics and analytics data:
	- message counts per user/time bucket (**not message content**),
	- voice session timing (join/leave timestamps, channel ID, total duration),
	- game/activity session timing and game name,
	- aggregated leaderboard/time-series metrics derived from those records.
- Operational logs: administrative action log entries, integrity checks, and export activity needed for support and abuse investigations.

## Why We Process Data
- Verify membership and assign/remove roles correctly.
- Operate voice automation features and permissions.
- Provide moderation tooling, auditability, and abuse prevention.
- Provide activity dashboards and server health/engagement analytics.

## How Deletion Requests Are Processed
- Users open a Discord support ticket requesting deletion.
- Staff verify ownership, then remove verification records, voice channel preferences, metrics records, and related audit entries using the existing admin tooling.
- Direct messages are not stored; we never archive message content.

## Retention
- Operational logs and audit entries are retained for a short operational window (typically 30–90 days, default ~60 days) unless a longer period is required for an active investigation.
- Metrics data retention defaults to **90 days** (configurable in `config/config.yaml` under `metrics.retention_days`).
- Retention helpers (manual and schedulable) exist to purge audit/log tables; staff can trigger cleanup after tickets close.
- The schema is current—there are no legacy migrations or backwards-compatibility tables pending cleanup.

## Recipients and Transfers
- Data is used internally by TEST Squadron operators and authorized staff.
- Data is not sold.
- Data may be processed by infrastructure providers required to run the bot/dashboard (hosting, Discord platform APIs).
- We do not intentionally transfer data outside required service operation paths.

## Data Minimization
- We do not store message content or tokens.
- Data is kept only to operate verification, role management, and voice automation features.
- Retention helpers are used conservatively to avoid unexpected production changes.

## User Rights
Subject to applicable law, users may request:
- access to their data,
- correction of inaccurate data,
- deletion (right to erasure),
- restriction or objection to processing,
- a copy of applicable data.

Users may also lodge a complaint with their local supervisory authority.
