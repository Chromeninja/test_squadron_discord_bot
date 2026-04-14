import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import SearchableSelect from '../components/SearchableSelect';
import SearchableMultiSelect from '../components/SearchableMultiSelect';
import {
  eventsApi,
  guildApi,
  type DiscordChannel,
  type EventModuleSettingsPayload,
  type GuildRole,
  type GuildInfo,
} from '../api/endpoints';
import { Alert, Badge, Button, Card, CardBody, Input, Textarea } from '../components/ui';
import {
  BUILDER_STEPS,
  DURATION_OPTIONS,
  calculateScheduledEndTime,
  combineDateAndTime,
  createDraftFromEvent,
  createEmptyDraft,
  formatDuration,
  formatEventDate,
  getAnnouncementChannelOptions,
  getEventChannelOptions,
  getReviewHighlights,
  type BuilderStep,
  type EndMode,
  type EventDraft,
  validateDraft,
} from './eventFlowShared';

interface EventEditorProps {
  guildId: string;
  mode: 'create' | 'edit';
}

function EventEditor({ guildId, mode }: EventEditorProps) {
  const navigate = useNavigate();
  const { eventId } = useParams<{ eventId: string }>();
  const [guildInfo, setGuildInfo] = useState<GuildInfo | null>(null);
  const [roles, setRoles] = useState<GuildRole[]>([]);
  const [channels, setChannels] = useState<DiscordChannel[]>([]);
  const [eventSettings, setEventSettings] = useState<EventModuleSettingsPayload | null>(null);
  const [builderStep, setBuilderStep] = useState<BuilderStep>('details');
  const [draft, setDraft] = useState<EventDraft>(() => createEmptyDraft(null));
  const [builderError, setBuilderError] = useState<string | null>(null);
  const [builderSaving, setBuilderSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const isEditing = mode === 'edit';
  const channelNameById = useMemo(() => new Map(channels.map((channel) => [channel.id, channel.name])), [channels]);
  const roleNameById = useMemo(() => new Map(roles.map((role) => [role.id, role.name])), [roles]);
  const eventChannelOptions = useMemo(() => getEventChannelOptions(channels), [channels]);
  const announcementChannelOptions = useMemo(() => getAnnouncementChannelOptions(channels), [channels]);
  const signupRoleOptions = useMemo(
    () => roles.map((role) => ({ id: role.id, name: role.name })),
    [roles],
  );
  const stepIndex = BUILDER_STEPS.findIndex((step) => step.id === builderStep);
  const validationError = validateDraft(draft);
  const computedEndTime = draft.startDate && draft.startTime
    ? calculateScheduledEndTime(draft)
    : null;
  const reviewHighlights = getReviewHighlights(draft);

  const updateDraft = useCallback((patch: Partial<EventDraft>) => {
    setDraft((currentDraft) => ({
      ...currentDraft,
      ...patch,
    }));
  }, []);

  const loadEditorData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const [guildResponse, configResponse, channelsResponse, rolesResponse] = await Promise.all([
        guildApi.getGuildInfo(guildId),
        guildApi.getGuildConfig(guildId),
        guildApi.getDiscordChannels(guildId),
        guildApi.getDiscordRoles(guildId),
      ]);

      setGuildInfo(guildResponse.guild);
      setEventSettings(configResponse.data.events);
      setChannels(channelsResponse.channels);
      setRoles(rolesResponse.roles);

      if (isEditing) {
        if (!eventId) {
          throw new Error('Missing event id');
        }

        const eventResponse = await eventsApi.getScheduledEvent(guildId, eventId);

        if (!eventResponse.event) {
          setError('The requested event could not be found.');
          return;
        }

        setDraft(createDraftFromEvent(eventResponse.event, configResponse.data.events));
      } else {
        setDraft(createEmptyDraft(configResponse.data.events));
      }
    } catch (err) {
      setError('Failed to load the event flow.');
    } finally {
      setLoading(false);
    }
  }, [eventId, guildId, isEditing]);

  useEffect(() => {
    void loadEditorData();
  }, [loadEditorData]);

  useEffect(() => {
    if (loading) {
      return;
    }

    setDraft((currentDraft) => {
      const nextDraft = { ...currentDraft };

      if (
        !nextDraft.channelId ||
        !eventChannelOptions.some((option) => option.id === nextDraft.channelId)
      ) {
        nextDraft.channelId = eventChannelOptions[0]?.id ?? null;
      }

      if (
        !nextDraft.announcementChannelId ||
        !announcementChannelOptions.some((option) => option.id === nextDraft.announcementChannelId)
      ) {
        nextDraft.announcementChannelId =
          eventSettings?.default_announcement_channel_id ?? announcementChannelOptions[0]?.id ?? null;
      }

      return nextDraft;
    });
  }, [announcementChannelOptions, eventChannelOptions, eventSettings, loading]);

  const goToNextStep = () => {
    if (builderStep === 'review') {
      return;
    }

    const nextStep = BUILDER_STEPS[stepIndex + 1];
    if (nextStep) {
      setBuilderStep(nextStep.id);
    }
  };

  const goToPreviousStep = () => {
    if (builderStep === 'details') {
      return;
    }

    const previousStep = BUILDER_STEPS[stepIndex - 1];
    if (previousStep) {
      setBuilderStep(previousStep.id);
    }
  };

  const handleSubmitEvent = async () => {
    const nextValidationError = validateDraft(draft);
    if (nextValidationError) {
      setBuilderError(nextValidationError);
      setBuilderStep('details');
      return;
    }

    setBuilderSaving(true);
    setBuilderError(null);

    try {
      const payload = {
        name: draft.name.trim(),
        description: draft.description.trim() || null,
        announcement_message:
          draft.announcementMessage.trim() || draft.description.trim() || null,
        scheduled_start_time: combineDateAndTime(draft.startDate, draft.startTime),
        scheduled_end_time: calculateScheduledEndTime(draft),
        entity_type: 'voice' as const,
        channel_id: draft.channelId,
        location: null,
        announcement_channel_id: draft.announcementChannelId,
        signup_role_ids: draft.signupRoleIds ?? [],
      };

      if (isEditing && eventId) {
        await eventsApi.updateScheduledEvent(guildId, eventId, payload);
      } else {
        await eventsApi.createScheduledEvent(guildId, payload);
      }

      navigate('/events');
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.response?.data?.error;
      setBuilderError(typeof detail === 'string' ? detail : 'Failed to save event.');
    } finally {
      setBuilderSaving(false);
    }
  };

  if (loading) {
    return <div className="py-8 text-center text-gray-300">Loading event flow...</div>;
  }

  return (
    <div className="space-y-6 lg:space-y-8">
      <div className="flex flex-col gap-4 rounded-[28px] border border-[#ffbb00]/18 bg-[radial-gradient(circle_at_top_left,_rgba(255,187,0,0.14),_transparent_28%),linear-gradient(135deg,_rgba(12,12,12,0.98),_rgba(28,20,2,0.92))] p-6 shadow-2xl shadow-black/30 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.3em] text-[#ffbb00]/70">Workspace / Events</p>
          <div className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <h2 className="text-3xl font-bold text-[#fff4cc]">{isEditing ? 'Edit event' : 'New event'}</h2>
            <span className="text-lg font-medium text-[#bba56b]">{guildInfo?.guild_name || 'Current guild'}</span>
          </div>
        </div>
        <Button variant="secondary" size="sm" onClick={() => navigate('/events')}>
          Back to Events
        </Button>
      </div>

      {error && <Alert variant="error">{error}</Alert>}

      {eventSettings?.enabled === false && (
        <Alert variant="warning">
          The event module is currently disabled for this guild. Native Discord events remain available, but new coordinator workflows should be considered inactive until a bot admin re-enables the module.
        </Alert>
      )}

      <div className="grid gap-6 lg:grid-cols-[220px_minmax(0,1fr)] xl:grid-cols-[220px_minmax(0,1.25fr)_320px]">
        <div>
          <nav className="relative rounded-[24px] border border-slate-800 bg-slate-950/60 p-4">
            <div className="absolute bottom-6 left-[1.55rem] top-6 hidden w-px bg-slate-700 md:block" />
            <ol className="relative space-y-4" role="list">
              {BUILDER_STEPS.map((step, index) => {
                const isActive = step.id === builderStep;
                const isComplete = index < stepIndex;

                return (
                  <li key={step.id}>
                    <button
                      type="button"
                      onClick={() => setBuilderStep(step.id)}
                      className="group flex w-full items-start gap-4 rounded-2xl px-2 py-1 text-left"
                    >
                      <div
                        className={[
                          'relative z-10 flex h-10 w-10 flex-none items-center justify-center rounded-full border-2 text-sm font-semibold transition',
                          isActive
                            ? 'border-[#ffbb00] bg-[#1f1804] text-[#fff4cc]'
                            : isComplete
                              ? 'border-emerald-500 bg-emerald-500/10 text-emerald-200'
                              : 'border-slate-700 bg-slate-900 text-slate-300',
                        ].join(' ')}
                      >
                        {isComplete ? '✓' : index + 1}
                      </div>
                      <div className="pt-1">
                        <p className={isActive ? 'text-sm font-semibold text-white' : 'text-sm font-semibold text-slate-200'}>{step.title}</p>
                        <p className="mt-1 text-xs leading-5 text-slate-400">{step.description}</p>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ol>
          </nav>
        </div>

        <div className="space-y-6">
          {builderError && <Alert variant="error">{builderError}</Alert>}

          <div className="rounded-[28px] border border-slate-800 bg-[linear-gradient(180deg,rgba(18,22,31,0.96),rgba(10,12,18,0.98))] p-6 shadow-xl shadow-black/20">
            <div className="mb-6 border-b border-slate-800 pb-5">
              <h3 className="text-2xl font-semibold text-white">{BUILDER_STEPS[stepIndex]?.title}</h3>
              <p className="mt-2 text-sm text-slate-400">{BUILDER_STEPS[stepIndex]?.description}</p>
            </div>

            {builderStep === 'details' && (
              <div className="space-y-5">
                <Input
                  label="Event Name"
                  value={draft.name}
                  onChange={(event) => updateDraft({ name: event.target.value })}
                  placeholder="e.g. Fleet Night"
                />

                <Textarea
                  label="Description"
                  value={draft.description}
                  onChange={(event) => {
                    const nextDescription = event.target.value;
                    updateDraft(
                      draft.announcementMessage.trim()
                        ? { description: nextDescription }
                        : {
                            description: nextDescription,
                            announcementMessage: nextDescription,
                          },
                    );
                  }}
                  placeholder="Add the mission brief, prep notes, or agenda"
                />

                <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                  <div className="rounded-2xl border border-slate-700 bg-slate-900/70 p-4">
                    <h4 className="text-sm font-semibold text-white">Start</h4>
                    <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <Input
                        id="start-date"
                        label="Start Date"
                        type="date"
                        value={draft.startDate}
                        onChange={(event) => updateDraft({ startDate: event.target.value })}
                      />
                      <Input
                        id="start-time"
                        label="Start Time"
                        type="time"
                        step={60}
                        value={draft.startTime}
                        onChange={(event) => updateDraft({ startTime: event.target.value })}
                      />
                    </div>
                  </div>

                  <div className="rounded-2xl border border-slate-700 bg-slate-900/70 p-4">
                    <h4 className="text-sm font-semibold text-white">Finish Strategy</h4>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {[
                        { id: 'duration', label: 'Use duration' },
                        { id: 'manual', label: 'Set end time' },
                        { id: 'open', label: 'Open-ended' },
                      ].map((option) => (
                        <button
                          key={option.id}
                          type="button"
                          onClick={() => updateDraft({ endMode: option.id as EndMode })}
                          className={[
                            'rounded-full border px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] transition',
                            draft.endMode === option.id
                              ? 'border-[#ffbb00]/60 bg-[#2b2006] text-[#fff1bf]'
                              : 'border-slate-600 bg-slate-800 text-slate-300 hover:border-slate-400',
                          ].join(' ')}
                        >
                          {option.label}
                        </button>
                      ))}
                    </div>

                    {draft.endMode === 'duration' && (
                      <div className="mt-4 space-y-3">
                        <div className="flex flex-wrap gap-2">
                          {DURATION_OPTIONS.map((option) => (
                            <button
                              key={option.value}
                              type="button"
                              onClick={() => updateDraft({ durationMinutes: option.value })}
                              className={[
                                'rounded-full border px-3 py-2 text-xs font-medium transition',
                                draft.durationMinutes === option.value
                                  ? 'border-[#ffbb00]/60 bg-[#2b2006] text-[#fff1bf]'
                                  : 'border-slate-600 bg-slate-800 text-slate-300 hover:border-slate-400',
                              ].join(' ')}
                            >
                              {option.label}
                            </button>
                          ))}
                        </div>
                        <Input
                          label="Custom Duration (minutes)"
                          type="number"
                          min={15}
                          step={15}
                          value={draft.durationMinutes}
                          onChange={(event) => updateDraft({ durationMinutes: event.target.value })}
                        />
                      </div>
                    )}

                    {draft.endMode === 'manual' && (
                      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
                        <Input
                          id="end-date"
                          label="End Date"
                          type="date"
                          value={draft.endDate}
                          onChange={(event) => updateDraft({ endDate: event.target.value })}
                        />
                        <Input
                          id="end-time"
                          label="End Time"
                          type="time"
                          step={60}
                          value={draft.endTime}
                          onChange={(event) => updateDraft({ endTime: event.target.value })}
                        />
                      </div>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                  <div>
                    <label className="mb-1 block text-sm font-medium text-gray-300">Event Channel</label>
                    <SearchableSelect
                      options={eventChannelOptions}
                      selected={draft.channelId}
                      onChange={(value) => updateDraft({ channelId: value })}
                      placeholder="Choose a voice channel"
                    />
                  </div>
                </div>
              </div>
            )}

            {builderStep === 'connections' && (
              <div className="space-y-5">
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-300">Announcement Channel</label>
                  <SearchableSelect
                    options={announcementChannelOptions}
                    selected={draft.announcementChannelId}
                    onChange={(value) => updateDraft({ announcementChannelId: value })}
                    placeholder="Choose a text channel"
                  />
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-300">Signup Roles (optional)</label>
                  <SearchableMultiSelect
                    options={signupRoleOptions}
                    selected={draft.signupRoleIds ?? []}
                    onChange={(value) => updateDraft({ signupRoleIds: value })}
                    placeholder="Type to search server roles..."
                    componentId="event-signup-roles"
                  />
                </div>

                <Textarea
                  label="Announcement Message"
                  value={draft.announcementMessage}
                  onChange={(event) => updateDraft({ announcementMessage: event.target.value })}
                  placeholder="Defaults to your event brief, but you can customize what gets posted."
                />

                <Card variant="default" className="border border-slate-700 bg-slate-900/80">
                  <CardBody>
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Connection Summary</p>
                    <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <div className="rounded-2xl border border-slate-700 bg-slate-800/70 p-3">
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Announcement Channel</p>
                        <p className="mt-1 text-sm text-slate-100">
                          {draft.announcementChannelId
                            ? channelNameById.get(draft.announcementChannelId) || 'Configured channel'
                            : 'No announcement channel selected'}
                        </p>
                      </div>
                      <div className="rounded-2xl border border-slate-700 bg-slate-800/70 p-3">
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Native Sync</p>
                        <p className="mt-1 text-sm text-slate-100">
                          {eventSettings?.default_native_sync === false
                            ? 'Manual coordinator sync posture'
                            : 'Native Discord sync enabled'}
                        </p>
                      </div>
                    </div>
                  </CardBody>
                </Card>
              </div>
            )}

            {builderStep === 'review' && (
              <div className="space-y-5">
                {validationError && <Alert variant="warning">{validationError}</Alert>}

                <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                  <Card variant="default" className="border border-slate-700 bg-slate-900/80">
                    <CardBody>
                      <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Publish Payload</p>
                      <div className="mt-4 space-y-3 text-sm text-slate-300">
                        <div className="flex items-center justify-between gap-4">
                          <span>Name</span>
                          <span className="text-right text-slate-100">{draft.name || 'Untitled event'}</span>
                        </div>
                        <div className="flex items-center justify-between gap-4">
                          <span>Type</span>
                          <span className="text-right text-slate-100">Voice event</span>
                        </div>
                        <div className="flex items-center justify-between gap-4">
                          <span>Starts</span>
                          <span className="text-right text-slate-100">
                            {draft.startDate && draft.startTime
                              ? formatEventDate(combineDateAndTime(draft.startDate, draft.startTime))
                              : 'Not set'}
                          </span>
                        </div>
                        <div className="flex items-center justify-between gap-4">
                          <span>Ends</span>
                          <span className="text-right text-slate-100">{formatEventDate(computedEndTime)}</span>
                        </div>
                        <div className="flex items-center justify-between gap-4">
                          <span>Connection</span>
                          <span className="text-right text-slate-100">
                            {draft.channelId
                              ? channelNameById.get(draft.channelId) || 'Configured voice channel'
                              : 'No voice channel selected'}
                          </span>
                        </div>
                        <div className="flex items-center justify-between gap-4">
                          <span>Announcement</span>
                          <span className="text-right text-slate-100">
                            {draft.announcementChannelId
                              ? channelNameById.get(draft.announcementChannelId) || 'Configured channel'
                              : 'Not set'}
                          </span>
                        </div>
                        <div className="flex items-center justify-between gap-4">
                          <span>Announcement Message</span>
                          <span className="text-right text-slate-100">
                            {(draft.announcementMessage.trim() || draft.description.trim())
                              ? `${(draft.announcementMessage.trim() || draft.description.trim()).slice(0, 40)}${(draft.announcementMessage.trim() || draft.description.trim()).length > 40 ? '...' : ''}`
                              : 'Default summary'}
                          </span>
                        </div>
                        <div className="flex items-center justify-between gap-4">
                          <span>Signup Roles</span>
                          <span className="text-right text-slate-100">
                            {(draft.signupRoleIds ?? []).length > 0
                              ? (draft.signupRoleIds ?? [])
                                  .map((roleId) => roleNameById.get(roleId) || `Role ${roleId}`)
                                  .join(', ')
                              : 'None'}
                          </span>
                        </div>
                      </div>
                    </CardBody>
                  </Card>

                  <Card variant="default" className="border border-slate-700 bg-slate-900/80">
                    <CardBody>
                      <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Summary</p>
                      <div className="mt-4 flex flex-wrap gap-2">
                        {reviewHighlights.map((highlight) => (
                          <span
                            key={highlight}
                            className="rounded-full border border-cyan-500/20 bg-cyan-500/10 px-3 py-1 text-xs font-medium text-cyan-100"
                          >
                            {highlight}
                          </span>
                        ))}
                      </div>
                    </CardBody>
                  </Card>
                </div>
              </div>
            )}

            <div className="mt-8 flex flex-col gap-3 border-t border-slate-800 pt-5 sm:flex-row sm:items-center sm:justify-between">
              <div className="text-xs uppercase tracking-[0.2em] text-slate-500">Step {stepIndex + 1} of {BUILDER_STEPS.length}</div>
              <div className="flex flex-wrap items-center gap-3">
                <Button variant="secondary" onClick={() => navigate('/events')}>Cancel</Button>
                <Button variant="secondary" onClick={goToPreviousStep} disabled={builderStep === 'details'}>
                  Back
                </Button>
                {builderStep === 'review' ? (
                  <Button
                    variant="success"
                    onClick={() => {
                      void handleSubmitEvent();
                    }}
                    loading={builderSaving}
                    disabled={!!validationError}
                  >
                    {builderSaving ? (isEditing ? 'Saving...' : 'Publishing...') : (isEditing ? 'Save Changes' : 'Publish Event')}
                  </Button>
                ) : (
                  <Button variant="success" onClick={goToNextStep}>
                    Continue
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="hidden space-y-4 xl:block">
          <Card variant="default" className="border border-slate-700 bg-slate-900/85">
            <CardBody>
              <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Live Preview</p>
              <div className="mt-4 rounded-[24px] border border-[#ffbb00]/15 bg-[linear-gradient(180deg,_rgba(58,41,5,0.35),_rgba(15,23,42,0.96))] p-5">
                <div className="flex flex-wrap gap-2">
                  <Badge variant="info">Voice</Badge>
                </div>
                <h4 className="mt-4 text-2xl font-semibold text-white">{draft.name || 'Untitled event'}</h4>
                <p className="mt-3 text-sm leading-6 text-slate-300">
                  {draft.description || 'Add a concise mission brief so members understand the event before they commit.'}
                </p>

                <div className="mt-5 space-y-3">
                  <div className="rounded-2xl border border-slate-700/80 bg-slate-900/50 p-3">
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Start</p>
                    <p className="mt-1 text-sm text-slate-100">
                      {draft.startDate && draft.startTime
                        ? formatEventDate(combineDateAndTime(draft.startDate, draft.startTime))
                        : 'Set a start date and time'}
                    </p>
                  </div>
                  <div className="rounded-2xl border border-slate-700/80 bg-slate-900/50 p-3">
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Duration</p>
                    <p className="mt-1 text-sm text-slate-100">
                      {draft.endMode === 'duration'
                        ? formatDuration(draft.durationMinutes)
                        : draft.endMode === 'manual'
                          ? formatEventDate(computedEndTime)
                          : 'Open-ended'}
                    </p>
                  </div>
                  <div className="rounded-2xl border border-slate-700/80 bg-slate-900/50 p-3">
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Destination</p>
                    <p className="mt-1 text-sm text-slate-100">
                      {draft.channelId
                        ? channelNameById.get(draft.channelId) || 'Configured voice channel'
                        : 'Select a voice channel'}
                    </p>
                  </div>
                </div>
              </div>
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}

export default EventEditor;
