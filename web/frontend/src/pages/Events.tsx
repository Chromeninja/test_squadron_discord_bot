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
    return <div className="py-8 text-center text-gray-300">Loading event coordination...</div>;
  }

  return (
    <div className="space-y-6 lg:space-y-8">
      <div className="flex flex-wrap items-center justify-end gap-3 rounded-[24px] border border-[#ffbb00]/18 bg-[linear-gradient(180deg,rgba(20,23,31,0.95),rgba(14,17,24,0.95))] p-4 shadow-lg shadow-black/20">
        <span className="inline-flex items-center px-2 py-0.5 text-xs font-semibold rounded bg-[#ffbb00]/12 text-[#ffe08a] border border-[#ffbb00]/25">{roleLabel}</span>
        <Button onClick={() => navigate('/events/new')} variant="success" size="sm">
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
      </div>

      {error && <Alert variant="error">{error}</Alert>}

      {eventSettings?.enabled === false && (
        <Alert variant="warning">
          The event module is currently disabled for this guild. Native Discord events remain visible for audit purposes, but coordinator workflows should be considered inactive until a bot admin re-enables the module in Settings.
        </Alert>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card variant="default" className="border border-slate-700 bg-slate-900/80">
          <CardBody>
            <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Defaults</p>
            <div className="mt-3 space-y-2 text-sm text-slate-300">
              <div className="flex items-center justify-between gap-4">
                <span>Native sync</span>
                <Badge variant={eventSettings?.default_native_sync === false ? 'neutral' : 'success'}>
                  {eventSettings?.default_native_sync === false ? 'Off' : 'On'}
                </Badge>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span>Announcement channel</span>
                <span className="text-right text-slate-200">{defaultAnnouncementLabel}</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span>Voice channel</span>
                <span className="text-right text-slate-200">{defaultVoiceLabel}</span>
              </div>
            </div>
          </CardBody>
        </Card>

        <Card variant="default" className="border border-slate-700 bg-slate-900/80">
          <CardBody>
            <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Live Inventory</p>
            <div className="mt-3">
              <p className="text-4xl font-bold text-white">{filteredEvents.length}</p>
              <p className="mt-1 text-sm text-slate-400">
                {inventoryLabel}
              </p>
              {scheduledEventsLoading && (
                <p className="mt-2 text-xs text-cyan-300">Refreshing event inventory...</p>
              )}
            </div>
          </CardBody>
        </Card>
      </div>

      {scheduledEventsError && <Alert variant="warning">{scheduledEventsError}</Alert>}

      <div className="space-y-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h3 className="text-xl font-semibold text-white">{sectionTitle}</h3>
            {guildInfo?.guild_name && <p className="mt-1 text-sm text-slate-500">{guildInfo.guild_name}</p>}
          </div>
        </div>

        {filteredEvents.length === 0 ? (
          <Card variant="default" className="border border-dashed border-slate-700 bg-slate-900/70">
            <CardBody>
              <h4 className="text-lg font-semibold text-white">{emptyStateTitle}</h4>
            </CardBody>
          </Card>
        ) : (
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            {filteredEvents.map((event) => (
              <Card key={event.id} variant="default" className="border border-slate-700 bg-slate-900/85">
                <CardBody>
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-xs uppercase tracking-[0.2em] text-cyan-300">{event.entity_type}</p>
                        <Badge variant={getStatusTone(event.status)}>{event.status}</Badge>
                      </div>
                      <h4 className="mt-2 text-xl font-semibold text-white">{event.name}</h4>
                    </div>
                  </div>

                  {event.description && <p className="mt-3 text-sm leading-6 text-slate-300">{event.description}</p>}

                  <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div className="rounded-2xl border border-slate-700 bg-slate-800/70 p-3">
                      <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Starts</p>
                      <p className="mt-1 text-sm text-slate-100">{formatEventDate(event.scheduled_start_time)}</p>
                    </div>
                    {event.recurrence_rule ? (
                      <div className="rounded-2xl border border-slate-700 bg-slate-800/70 p-3">
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Repeats</p>
                        <p className="mt-1 text-sm text-slate-100">{event.recurrence_rule}</p>
                      </div>
                    ) : (
                      <div className="rounded-2xl border border-slate-700 bg-slate-800/70 p-3">
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Ends</p>
                        <p className="mt-1 text-sm text-slate-100">{formatEventDate(event.scheduled_end_time)}</p>
                      </div>
                    )}
                    <div className="rounded-2xl border border-slate-700 bg-slate-800/70 p-3">
                      <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Connection</p>
                      <p className="mt-1 text-sm text-slate-100">{event.channel_name || event.location || 'No channel attached'}</p>
                    </div>
                    <div className="rounded-2xl border border-slate-700 bg-slate-800/70 p-3">
                      <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Interested</p>
                      <p className="mt-1 text-sm text-slate-100">{event.user_count} member{event.user_count === 1 ? '' : 's'}</p>
                    </div>
                  </div>

                  {(event.creator_name || event.location) && (
                    <div className="mt-4 flex flex-wrap gap-3 text-xs text-slate-400">
                      {event.creator_name && <span>Created by {event.creator_name}</span>}
                      {event.location && <span>Location: {event.location}</span>}
                    </div>
                  )}

                  <div className="mt-4 flex flex-wrap gap-2">
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
                </CardBody>
              </Card>
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
