# Activity Metrics

## Purpose

Metrics record aggregate voice time, message counts, and game/activity data for
guild dashboards. Message content is not read or stored.

## Collection flow

Gateway voice, message, presence, and member events are converted into bounded
activity records. The service flushes records to the metrics database and
applies the configured retention period. Excluded channels are honored during
live collection and startup backfill.

## Code ownership

- Event collection: `cogs/metrics/` and `services/metrics_activity.py`.
- Aggregation/flush: `services/metrics_buckets.py` and `services/metrics_flush.py`.
- Queries and models: `services/metrics_queries.py`, `services/metrics_read.py`,
  and `services/metrics_models.py`.
- API boundary: `backend/api/internal/metrics.py`, `connectors/metrics.py`, and
  dashboard metrics routes.

Metrics access is restricted to Discord Manager or higher. Per-user deletion is
available through the authorized dashboard API. Presence and Server Members
intents must be enabled for the relevant data; Message Content is not required.
