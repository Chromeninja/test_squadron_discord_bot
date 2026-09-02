import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  eventsApi,
  guildApi,
  type DiscordChannel,
  type EventModuleSettingsPayload,
  type ScheduledEventSummary,
} from '../api/endpoints';
import { Alert, Badge, Button, Card, CardBody, ConfirmationModal } from '../components/ui';
import { EventSignupPanel } from '../components/events/EventSignupPanel';
import { EventRoleManager } from '../components/events/EventRoleManager';
import { EventRosterPanel } from '../components/events/EventRosterPanel';
import { EventMessagePanel } from '../components/events/EventMessagePanel';
import { EventSignupExportButton } from '../components/events/EventSignupExportButton';
import { useAuth } from '../contexts/AuthContext';
import { useRequestSequence } from '../hooks/useRequestSequence';
import {
  formatEventDate,
  formatRecurrencePayloadSummary,
  getStatusTone,
} from './eventFlowShared';
import { EventPageHeader } from './eventPageChrome';

interface EventsProps {
  guildId: string;
  view?: 'active' | 'past';
}

function getEventRecurrenceLabel(event: ScheduledEventSummary): string | null {
  return event.recurrence_rule || formatRecurrencePayloadSummary(event.recurrence_rule_payload);
}

function getEventConnectionLabel(
  event: ScheduledEventSummary,
  channelNameById: Map<string, string>,
): string {
  if (event.channel_name) {
    return event.channel_name;
  }

  if (event.channel_id) {
    const channelName = channelNameById.get(event.channel_id);
    if (channelName) {
      return channelName;
    }
  }

  return event.location || 'No channel attached';
}

function Events({ guildId, view = 'active' }: EventsProps) {
  const navigate = useNavigate();
  const { userHasPermission } = useAuth();
  const isCoordinator = userHasPermission('event_coordinator');
  const coreRequestSequence = useRequestSequence();
  const eventsRequestSequence = useRequestSequence();
  const [channels, setChannels] = useState<DiscordChannel[]>([]);
  const [eventSettings, setEventSettings] = useState<EventModuleSettingsPayload | null>(null);
  const [scheduledEvents, setScheduledEvents] = useState<ScheduledEventSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scheduledEventsLoading, setScheduledEventsLoading] = useState(false);
  const [scheduledEventsError, setScheduledEventsError] = useState<string | null>(null);
  const [eventPendingDelete, setEventPendingDelete] = useState<ScheduledEventSummary | null>(null);
  const [deletingEvent, setDeletingEvent] = useState(false);

  const channelNameById = useMemo(() => {
    return new Map(channels.map((channel) => [channel.id, channel.name]));
  }, [channels]);

  const loadCoreData = useCallback(async () => {
    const requestId = coreRequestSequence.next();
    setError(null);

    try {
      const [configResponse, channelsResponse] = await Promise.all([
        guildApi.getGuildConfig(guildId),
        guildApi.getDiscordChannels(guildId),
      ]);

      if (!coreRequestSequence.isCurrent(requestId)) {
        return;
      }

      setEventSettings(configResponse.data.events);
      setChannels(channelsResponse.channels);
    } catch {
      if (!coreRequestSequence.isCurrent(requestId)) {
        return;
      }

      setError('Failed to load event coordination data.');
    } finally {
      if (coreRequestSequence.isCurrent(requestId)) {
        setLoading(false);
      }
    }
  }, [coreRequestSequence, guildId]);

  const loadScheduledEvents = useCallback(async () => {
    const requestId = eventsRequestSequence.next();
    setScheduledEventsLoading(true);
    setScheduledEventsError(null);

    try {
      const eventsResponse = await eventsApi.getScheduledEvents(guildId);

      if (!eventsRequestSequence.isCurrent(requestId)) {
        return;
      }

      setScheduledEvents(eventsResponse.events);
    } catch {
      if (!eventsRequestSequence.isCurrent(requestId)) {
        return;
      }

      setScheduledEvents([]);
      setScheduledEventsError('Scheduled events are taking too long to load right now. You can still build a new event plan below.');
    } finally {
      if (eventsRequestSequence.isCurrent(requestId)) {
        setScheduledEventsLoading(false);
      }
    }
  }, [eventsRequestSequence, guildId]);

  useEffect(() => {
    void loadCoreData();
    void loadScheduledEvents();
  }, [loadCoreData, loadScheduledEvents]);

  const handleSyncFromDiscord = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    setScheduledEventsError(null);

    try {
      const syncResponse = await eventsApi.syncScheduledEvents(guildId, {
        direction: 'reconcile',
      });
      setScheduledEvents(syncResponse.events);
      await loadCoreData();
      await loadScheduledEvents();
    } catch {
      setError('Failed to sync scheduled events from Discord.');
      await loadScheduledEvents();
    } finally {
      setRefreshing(false);
    }
  }, [guildId, loadCoreData, loadScheduledEvents]);

  const handleDeleteEvent = useCallback(async () => {
    if (!eventPendingDelete) {
      return;
    }

    setDeletingEvent(true);
    setError(null);

    try {
      await eventsApi.deleteScheduledEvent(guildId, eventPendingDelete.id);
      setScheduledEvents((previous) =>
        previous.filter((event) => event.id !== eventPendingDelete.id)
      );
      setEventPendingDelete(null);
    } catch {
      setError(`Failed to delete "${eventPendingDelete.name}".`);
    } finally {
      setDeletingEvent(false);
    }
  }, [eventPendingDelete, guildId]);

  const isPastEvent = useCallback((event: ScheduledEventSummary): boolean => {
    const normalizedStatus = event.status.toLowerCase();
    const terminalStatuses = new Set(['completed', 'ended', 'cancelled', 'canceled']);
    if (terminalStatuses.has(normalizedStatus)) {
      return true;
    }

    // Recurring events can have an old anchor date while still being active.
    if (getEventRecurrenceLabel(event)) {
      return false;
    }

    const now = Date.now();
    const endTs = event.scheduled_end_time ? Date.parse(event.scheduled_end_time) : Number.NaN;
    if (!Number.isNaN(endTs) && endTs < now) {
      return true;
    }

    const startTs = event.scheduled_start_time ? Date.parse(event.scheduled_start_time) : Number.NaN;
    const explicitlyActiveStatuses = new Set(['active', 'in_progress', 'ongoing']);
    if (!Number.isNaN(startTs) && startTs < now && !explicitlyActiveStatuses.has(normalizedStatus)) {
      return true;
    }

    return false;
  }, []);

  const filteredEvents = useMemo(() => {
    return scheduledEvents.filter((event) => (view === 'past' ? isPastEvent(event) : !isPastEvent(event)));
  }, [isPastEvent, scheduledEvents, view]);

  const emptyStateTitle =
    view === 'past' ? 'No past events yet' : 'No active or upcoming events right now';
  const scheduledEventsSummary = `${filteredEvents.length} Scheduled event${filteredEvents.length === 1 ? '' : 's'}`;

  if (loading) {
    return (
      <Card variant="default">
        <CardBody className="py-10 text-center text-gray-300">
          Loading event coordination...
        </CardBody>
      </Card>
    );
  }

  return (
    <div className="space-y-6 lg:space-y-8">
      <EventPageHeader
        eyebrow="Events"
        description={scheduledEventsSummary}
        actions={
          isCoordinator ? (
            <>
              <Button onClick={() => navigate(`/dashboard/${encodeURIComponent(guildId)}/events/new`)} variant="primary" size="sm">
                New Event
              </Button>
              <Button
                onClick={() => {
                  void handleSyncFromDiscord();
                }}
                loading={refreshing}
                variant="secondary"
                size="sm"
              >
                {refreshing ? 'Syncing...' : 'Sync From Discord'}
              </Button>
            </>
          ) : undefined
        }
      />

      {error && <Alert variant="error">{error}</Alert>}

      {eventSettings?.enabled === false && (
        <Alert variant="warning">
          The event module is currently disabled for this guild. Native Discord events remain visible for audit purposes, but coordinator workflows should be considered inactive until a bot admin re-enables the module in Settings.
        </Alert>
      )}

      {scheduledEventsError && <Alert variant="warning">{scheduledEventsError}</Alert>}

      {scheduledEventsLoading ? (
        <p className="text-xs uppercase tracking-[0.18em] text-[#ffbb00]/70">Refreshing inventory...</p>
      ) : null}

      <div className="space-y-4">
        {filteredEvents.length === 0 ? (
          <Card variant="ghost" className="border-dashed">
            <CardBody className="space-y-4 py-8">
              <h4 className="text-lg font-semibold text-[#fff4cc]">{emptyStateTitle}</h4>
              <p className="max-w-2xl text-sm leading-6 text-slate-400">
                {view === 'past'
                  ? 'Past events appear here after they end or move into a terminal status.'
                  : isCoordinator
                    ? 'Create an event or sync from Discord to bring the live schedule into this workspace.'
                    : 'There are no active or upcoming events right now. Check back soon!'}
              </p>
              {view === 'active' && isCoordinator ? (
                <div className="flex flex-wrap gap-3">
                  <Button variant="primary" onClick={() => navigate(`/dashboard/${encodeURIComponent(guildId)}/events/new`)}>
                    Create Event
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => {
                      void handleSyncFromDiscord();
                    }}
                    loading={refreshing}
                  >
                    Refresh from Discord
                  </Button>
                </div>
              ) : null}
            </CardBody>
          </Card>
        ) : (
          <div className="divide-y divide-[rgba(255,187,0,0.08)]">
            {filteredEvents.map((event) => {
              const recurrenceLabel = getEventRecurrenceLabel(event);
              const connectionLabel = getEventConnectionLabel(event, channelNameById);

              return (
                <div key={event.id} className="space-y-4 py-6">
                  {event.image_url ? (
                    <div className="overflow-hidden rounded-2xl border border-[rgba(255,187,0,0.12)] bg-[#120d00]/60">
                      <img
                        src={event.image_url}
                        alt={`${event.name} event artwork`}
                        loading="lazy"
                        className="h-40 w-full object-cover sm:h-48"
                      />
                    </div>
                  ) : null}
                  <div className="flex items-start justify-between gap-4">
                    <div className="space-y-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-[11px] uppercase tracking-[0.24em] text-[#ffbb00]/70">{event.entity_type}</p>
                        <Badge variant={getStatusTone(event.status)}>{event.status}</Badge>
                        {recurrenceLabel ? <Badge variant="neutral">Recurring</Badge> : null}
                      </div>
                      <div>
                        <h4 className="text-xl font-semibold text-[#fff4cc]">{event.name}</h4>
                        {event.description ? (
                          <p className="mt-2 text-sm leading-6 text-[#d4c39b]">{event.description}</p>
                        ) : (
                          <p className="mt-2 text-sm text-[#a89465]">No briefing added yet.</p>
                        )}
                      </div>
                    </div>
                    <div className="rounded-2xl border border-[rgba(255,187,0,0.12)] bg-[#120d00]/60 px-3 py-2 text-right">
                      <p className="text-[11px] uppercase tracking-[0.22em] text-[#a89465]">Interested</p>
                      <p className="mt-1 text-sm font-medium text-[#f5deb3]">
                        {event.user_count} member{event.user_count === 1 ? '' : 's'}
                      </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div className="rounded-2xl border border-[rgba(255,187,0,0.12)] bg-[#120d00]/60 p-3">
                      <p className="text-[11px] uppercase tracking-[0.22em] text-[#a89465]">Starts</p>
                      <p className="mt-2 text-sm leading-6 text-[#f5deb3]">
                        {formatEventDate(event.scheduled_start_time)}
                      </p>
                    </div>
                    <div className="rounded-2xl border border-[rgba(255,187,0,0.12)] bg-[#120d00]/60 p-3">
                      <p className="text-[11px] uppercase tracking-[0.22em] text-[#a89465]">
                        {recurrenceLabel ? 'Repeats' : 'Ends'}
                      </p>
                      <p className="mt-2 text-sm leading-6 text-[#f5deb3]">
                        {recurrenceLabel || formatEventDate(event.scheduled_end_time)}
                      </p>
                    </div>
                    <div className="rounded-2xl border border-[rgba(255,187,0,0.12)] bg-[#120d00]/60 p-3">
                      <p className="text-[11px] uppercase tracking-[0.22em] text-[#a89465]">Connection</p>
                      <p className="mt-2 text-sm leading-6 text-[#f5deb3]">
                        {connectionLabel}
                      </p>
                    </div>
                  </div>

                  <div className="flex flex-col gap-3 border-t border-[rgba(255,187,0,0.1)] pt-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex flex-wrap items-center gap-2 text-xs text-[#a89465]">
                      {event.creator_name ? (
                        <span className="rounded-full border border-[rgba(255,187,0,0.12)] bg-[#120d00]/60 px-3 py-1.5">
                          Created by {event.creator_name}
                        </span>
                      ) : null}
                      {event.location ? (
                        <span className="rounded-full border border-[rgba(255,187,0,0.12)] bg-[#120d00]/60 px-3 py-1.5">
                          Location: {event.location}
                        </span>
                      ) : null}
                    </div>

                    {isCoordinator ? (
                      <div className="flex flex-wrap gap-2">
                        <EventSignupExportButton guildId={guildId} eventId={event.id} />
                        <Button
                          variant="secondary"
                          size="sm"
                          aria-label={`Edit ${event.name}`}
                          onClick={() => navigate(`/dashboard/${encodeURIComponent(guildId)}/events/${event.id}/edit`)}
                        >
                          Edit Event
                        </Button>
                        <Button
                          variant="danger"
                          size="sm"
                          aria-label={`Delete ${event.name}`}
                          onClick={() => setEventPendingDelete(event)}
                        >
                          Delete Event
                        </Button>
                      </div>
                    ) : null}
                  </div>

                  {/* Member signup controls (active/upcoming/recurring only) */}
                  {!isPastEvent(event) ? (
                    <EventSignupPanel
                      guildId={guildId}
                      event={event}
                      canSignup
                      onChanged={loadScheduledEvents}
                    />
                  ) : null}

                  {/* Coordinator management panels */}
                  {isCoordinator ? (
                    <div className="space-y-4">
                      <EventRoleManager
                        guildId={guildId}
                        eventId={event.id}
                        onChanged={loadScheduledEvents}
                      />
                      <EventRosterPanel
                        guildId={guildId}
                        eventId={event.id}
                        discordUserCount={event.user_count}
                      />
                      <EventMessagePanel
                        guildId={guildId}
                        eventId={event.id}
                        channels={channels}
                      />
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
      </div>

      <ConfirmationModal
        open={eventPendingDelete !== null}
        onClose={() => {
          if (!deletingEvent) {
            setEventPendingDelete(null);
          }
        }}
        onConfirm={() => {
          void handleDeleteEvent();
        }}
        title="Delete Event"
        message={
          eventPendingDelete
            ? `Delete "${eventPendingDelete.name}"? This cannot be undone.`
            : 'Delete this event? This cannot be undone.'
        }
        confirmText="Delete"
        cancelText="Cancel"
        variant="danger"
        loading={deletingEvent}
      />
    </div>
  );
}

export default Events;
