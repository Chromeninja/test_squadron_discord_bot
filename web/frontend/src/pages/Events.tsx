import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  eventsApi,
  guildApi,
  type DiscordChannel,
  type EventModuleSettingsPayload,
  type GuildInfo,
  type ScheduledEventSummary,
} from '../api/endpoints';
import { Alert, Badge, Button, Card, CardBody, ConfirmationModal } from '../components/ui';
import { useAuth } from '../contexts/AuthContext';
import { useRequestSequence } from '../hooks/useRequestSequence';
import { getRoleDisplayName } from '../utils/permissions';
import { formatEventDate, getStatusTone } from './eventFlowShared';
import { EventPageHeader, EventStatCard, EventViewTabs } from './eventPageChrome';

interface EventsProps {
  guildId: string;
  view?: 'active' | 'past';
}

function Events({ guildId, view = 'active' }: EventsProps) {
  const navigate = useNavigate();
  const { user, getUserRoleLevel } = useAuth();
  const coreRequestSequence = useRequestSequence();
  const eventsRequestSequence = useRequestSequence();
  const [guildInfo, setGuildInfo] = useState<GuildInfo | null>(null);
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
      const [guildResponse, configResponse, channelsResponse] = await Promise.all([
        guildApi.getGuildInfo(guildId),
        guildApi.getGuildConfig(guildId),
        guildApi.getDiscordChannels(guildId),
      ]);

      if (!coreRequestSequence.isCurrent(requestId)) {
        return;
      }

      setGuildInfo(guildResponse.guild);
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

  const roleLabel = useMemo(() => {
    if (!user) {
      return 'User';
    }

    return getRoleDisplayName(getUserRoleLevel());
  }, [getUserRoleLevel, user]);

  const isPastEvent = useCallback((event: ScheduledEventSummary): boolean => {
    const normalizedStatus = event.status.toLowerCase();
    const terminalStatuses = new Set(['completed', 'ended', 'cancelled', 'canceled']);
    if (terminalStatuses.has(normalizedStatus)) {
      return true;
    }

    // Recurring events can have an old anchor date while still being active.
    if (event.recurrence_rule) {
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

  const sectionTitle = view === 'past' ? 'Past events' : 'Active and upcoming events';
  const emptyStateTitle =
    view === 'past' ? 'No past events yet' : 'No active or upcoming events right now';
  const pageDescription =
    view === 'past'
      ? 'Review completed and older scheduled events without the setup noise of the live coordination view.'
      : 'Coordinate upcoming Discord events, keep destinations aligned, and scan the next actions without digging through extra chrome.';
  const inventoryLabel =
    view === 'past'
      ? 'past scheduled events visible in this view'
      : 'active or upcoming scheduled events visible in this view';

  const defaultAnnouncementLabel = eventSettings?.default_announcement_channel_id
    ? channelNameById.get(eventSettings.default_announcement_channel_id) || 'Configured channel'
    : 'Not configured';
  const defaultVoiceLabel = eventSettings?.default_voice_channel_id
    ? channelNameById.get(eventSettings.default_voice_channel_id) || 'Configured channel'
    : 'Not configured';

  if (loading) {
    return (
      <Card variant="default">
        <CardBody className="py-10 text-center text-gray-300">
          Loading event coordination...
        </CardBody>
      </Card>
    );
  }

  const tabs = [
    {
      key: 'active',
      label: 'Active',
      active: view === 'active',
      onClick: () => navigate('/events'),
    },
    {
      key: 'past',
      label: 'Past',
      active: view === 'past',
      onClick: () => navigate('/events/past'),
    },
  ];

  return (
    <div className="space-y-6 lg:space-y-8">
      <EventPageHeader
        title={sectionTitle}
        subtitle={guildInfo?.guild_name || 'Current guild'}
        description={pageDescription}
        actions={
          <>
            <Badge variant="info">{roleLabel}</Badge>
            <Button onClick={() => navigate('/events/new')} variant="primary" size="sm">
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
        }
        footer={
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <EventViewTabs tabs={tabs} />
            <div className="grid gap-3 sm:grid-cols-3 lg:min-w-[42rem] lg:flex-1">
              <EventStatCard
                label="Shown"
                value={<span className="text-2xl font-semibold text-white">{filteredEvents.length}</span>}
                supportingText={inventoryLabel}
              />
              <EventStatCard
                label="Announcement"
                value={defaultAnnouncementLabel}
                supportingText="Default posting destination"
              />
              <EventStatCard
                label="Voice"
                value={defaultVoiceLabel}
                supportingText={eventSettings?.default_native_sync === false ? 'Manual sync posture' : 'Native sync enabled'}
              />
            </div>
          </div>
        }
      />

      {error && <Alert variant="error">{error}</Alert>}

      {eventSettings?.enabled === false && (
        <Alert variant="warning">
          The event module is currently disabled for this guild. Native Discord events remain visible for audit purposes, but coordinator workflows should be considered inactive until a bot admin re-enables the module in Settings.
        </Alert>
      )}

      {scheduledEventsError && <Alert variant="warning">{scheduledEventsError}</Alert>}

      <div className="space-y-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h3 className="text-xl font-semibold text-[#fff4cc]">Event schedule</h3>
            <p className="mt-1 text-sm text-[#a89465]">
              {filteredEvents.length === 0
                ? 'Nothing needs attention in this view right now.'
                : `${filteredEvents.length} event${filteredEvents.length === 1 ? '' : 's'} ready to scan.`}
            </p>
          </div>
          {scheduledEventsLoading ? (
            <p className="text-xs uppercase tracking-[0.18em] text-[#ffbb00]/70">Refreshing inventory...</p>
          ) : null}
        </div>

        {filteredEvents.length === 0 ? (
          <Card variant="ghost" className="border-dashed">
            <CardBody className="space-y-4 py-8">
              <h4 className="text-lg font-semibold text-[#fff4cc]">{emptyStateTitle}</h4>
              <p className="max-w-2xl text-sm leading-6 text-slate-400">
                {view === 'past'
                  ? 'Past events appear here after they end or move into a terminal status.'
                  : 'Create an event or sync from Discord to bring the live schedule into this workspace.'}
              </p>
              {view === 'active' ? (
                <div className="flex flex-wrap gap-3">
                  <Button variant="primary" onClick={() => navigate('/events/new')}>
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
            {filteredEvents.map((event) => (
              <div key={event.id} className="space-y-4 py-6">
                  <div className="flex items-start justify-between gap-4">
                    <div className="space-y-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-[11px] uppercase tracking-[0.24em] text-[#ffbb00]/70">{event.entity_type}</p>
                        <Badge variant={getStatusTone(event.status)}>{event.status}</Badge>
                        {event.recurrence_rule ? <Badge variant="neutral">Recurring</Badge> : null}
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
                        {event.recurrence_rule ? 'Repeats' : 'Ends'}
                      </p>
                      <p className="mt-2 text-sm leading-6 text-[#f5deb3]">
                        {event.recurrence_rule || formatEventDate(event.scheduled_end_time)}
                      </p>
                    </div>
                    <div className="rounded-2xl border border-[rgba(255,187,0,0.12)] bg-[#120d00]/60 p-3">
                      <p className="text-[11px] uppercase tracking-[0.22em] text-[#a89465]">Connection</p>
                      <p className="mt-2 text-sm leading-6 text-[#f5deb3]">
                        {event.channel_name || event.location || 'No channel attached'}
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

                    <div className="flex flex-wrap gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      aria-label={`Edit ${event.name}`}
                      onClick={() => navigate(`/events/${event.id}/edit`)}
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
                  </div>
              </div>
            ))}
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
