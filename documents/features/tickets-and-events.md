# Tickets and Events

## Tickets

Ticket forms collect a request, create the configured Discord ticket structure,
and route staff actions through persistent views. Ticket state and statistics
are stored through the backend repositories and exposed through typed
connectors/API routes.

Key ownership areas include `cogs/tickets/`, `helpers/ticket_*`,
`services/ticket_*`, `backend/db/repository/tickets*`, and
`connectors/tickets.py`. Preserve permission checks, rate limits, and safe
handling of user-submitted content.

## Managed events

Managed events are stored in the backend first, then projected to Discord
scheduled events by the synchronization loop. The event's `sync_status` is
visible in the dashboard. Event repositories and API routes own persistence;
Discord synchronization belongs to the bot service layer.

Test guild isolation, duplicate handling, Discord API failures, and pending
sync recovery.
