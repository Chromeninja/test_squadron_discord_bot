import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  eventsApi,
  guildApi,
  type DiscordChannel,
  type EventModuleSettingsPayload,
  type GuildInfo,
  type GuildRole,
} from '../api/endpoints';
import { Alert, Badge, Button, Card, CardBody } from '../components/ui';
import {
  BUILDER_STEPS,
  buildRecurrenceRule,
  calculateScheduledEndTime,
  combineDateAndTime,
  createDraftFromEvent,
  createEmptyDraft,
  formatEventDate,
  getAnnouncementChannelOptions,
  getEventChannelOptions,
  getReviewHighlights,
  type BuilderStep,
  type EventDraft,
  validateDraft,
} from './eventFlowShared';
import { ConnectionsStep, DetailsStep, ReviewStep } from './EventEditorSteps';
import {
  StepNavigator,
} from './EventEditorComponents';
import { EventPageHeader, EventStatCard } from './eventPageChrome';

interface EventEditorProps {
  guildId: string;
  mode: 'create' | 'edit';
}

const STEP_SEQUENCE: BuilderStep[] = ['details', 'connections', 'review'];

function getStepValidationError(step: BuilderStep, draft: EventDraft): string | null {
  if (step === 'details') {
    if (!draft.name.trim()) {
      return 'Add an event name before moving on.';
    }

    if (!draft.startDate || !draft.startTime) {
      return 'Set the event start date and time before continuing.';
    }

    if (draft.endMode === 'manual' && ((!draft.endDate && draft.endTime) || (draft.endDate && !draft.endTime))) {
      return 'Provide both end date and end time when using a manual finish.';
    }

    if (draft.endMode === 'duration') {
      const durationMinutes = Number(draft.durationMinutes);
      if (!Number.isFinite(durationMinutes) || durationMinutes <= 0) {
        return 'Choose a valid duration before continuing.';
      }
    }

    if (draft.recurrenceEnabled) {
      const intervalRaw = Number(draft.recurrenceInterval);
      if (!Number.isFinite(intervalRaw) || intervalRaw <= 0) {
        return 'Recurring events need a valid interval.';
      }

      if (draft.recurrenceFrequency === 2 && draft.recurrenceWeekdays.length === 0) {
        return 'Weekly recurrence needs at least one weekday selected.';
      }
    }

    return null;
  }

  if (step === 'connections') {
    if (!draft.channelId) {
      return 'Choose a voice destination before continuing.';
    }

    if (!draft.announcementChannelId) {
      return 'Choose where the announcement should be posted.';
    }

    return null;
  }

  return validateDraft(draft);
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
  const channelNameById = useMemo(
    () => new Map(channels.map((channel) => [channel.id, channel.name])),
    [channels]
  );
  const roleNameById = useMemo(() => new Map(roles.map((role) => [role.id, role.name])), [roles]);
  const eventChannelOptions = useMemo(() => getEventChannelOptions(channels), [channels]);
  const announcementChannelOptions = useMemo(() => getAnnouncementChannelOptions(channels), [channels]);
  const signupRoleOptions = useMemo(
    () => roles.map((role) => ({ id: role.id, name: role.name })),
    [roles]
  );
  const stepIndex = BUILDER_STEPS.findIndex((step) => step.id === builderStep);
  const validationError = validateDraft(draft);
  const currentStepError = getStepValidationError(builderStep, draft);
  const computedEndTime = draft.startDate && draft.startTime ? calculateScheduledEndTime(draft) : null;
  const reviewHighlights = getReviewHighlights(draft);
  const currentStep = BUILDER_STEPS[stepIndex];
  const startSummary =
    draft.startDate && draft.startTime
      ? formatEventDate(combineDateAndTime(draft.startDate, draft.startTime))
      : 'Schedule not set';
  const destinationSummary = draft.channelId
    ? channelNameById.get(draft.channelId) || 'Configured voice channel'
    : 'Pick in connections';

  const updateDraft = useCallback((patch: Partial<EventDraft>) => {
    setBuilderError(null);
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
    } catch {
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

      if (!nextDraft.channelId || !eventChannelOptions.some((option) => option.id === nextDraft.channelId)) {
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

  const attemptStepChange = useCallback(
    (nextStep: BuilderStep) => {
      const nextIndex = STEP_SEQUENCE.indexOf(nextStep);

      if (nextIndex > stepIndex) {
        const nextError = getStepValidationError(builderStep, draft);
        if (nextError) {
          setBuilderError(nextError);
          return;
        }
      }

      setBuilderError(null);
      setBuilderStep(nextStep);
    },
    [builderStep, draft, stepIndex]
  );

  const goToNextStep = useCallback(() => {
    if (builderStep === 'review') {
      return;
    }

    const nextStep = STEP_SEQUENCE[stepIndex + 1];
    if (nextStep) {
      attemptStepChange(nextStep);
    }
  }, [attemptStepChange, builderStep, stepIndex]);

  const goToPreviousStep = useCallback(() => {
    if (builderStep === 'details') {
      return;
    }

    setBuilderError(null);
    const previousStep = STEP_SEQUENCE[stepIndex - 1];
    if (previousStep) {
      setBuilderStep(previousStep);
    }
  }, [builderStep, stepIndex]);

  const handleSubmitEvent = async () => {
    const nextValidationError = validateDraft(draft);
    if (nextValidationError) {
      setBuilderError(nextValidationError);

      if (getStepValidationError('details', draft)) {
        setBuilderStep('details');
      } else if (getStepValidationError('connections', draft)) {
        setBuilderStep('connections');
      } else {
        setBuilderStep('review');
      }

      return;
    }

    setBuilderSaving(true);
    setBuilderError(null);

    try {
      const payload = {
        name: draft.name.trim(),
        description: draft.description.trim() || null,
        announcement_message: draft.announcementMessage.trim() || draft.description.trim() || null,
        scheduled_start_time: combineDateAndTime(draft.startDate, draft.startTime),
        scheduled_end_time: calculateScheduledEndTime(draft),
        entity_type: 'voice' as const,
        channel_id: draft.channelId,
        location: null,
        announcement_channel_id: draft.announcementChannelId,
        signup_role_ids: draft.signupRoleIds ?? [],
        recurrence_rule: buildRecurrenceRule(draft),
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
    return (
      <Card variant="default">
        <CardBody className="py-10 text-center text-[#d4c39b]">Loading event flow...</CardBody>
      </Card>
    );
  }

  return (
    <div className="space-y-6 lg:space-y-8">
      <EventPageHeader
        title={isEditing ? 'Edit event' : 'New event'}
        subtitle={guildInfo?.guild_name || 'Current guild'}
        description="Build the event in three passes: define the schedule, connect it to the right channels, then review what members will actually see."
        actions={
          <Button variant="secondary" size="sm" onClick={() => navigate('/events')}>
            Back to Events
          </Button>
        }
        footer={
          <div className="grid gap-3 sm:grid-cols-3">
            <EventStatCard
              label="Current step"
              value={
                <span className="flex items-center gap-2">
                  <Badge variant="info">{`Step ${stepIndex + 1}`}</Badge>
                  <span>{currentStep?.title}</span>
                </span>
              }
              supportingText={currentStep?.description}
            />
            <EventStatCard label="Schedule" value={startSummary} supportingText="Start date and time for the next publish." />
            <EventStatCard label="Destination" value={destinationSummary} supportingText="Voice channel used for the event itself." />
          </div>
        }
      />

      {error && <Alert variant="error">{error}</Alert>}

      {eventSettings?.enabled === false && (
        <Alert variant="warning">
          The event module is currently disabled for this guild. Native Discord events remain available, but new coordinator workflows should be considered inactive until a bot admin re-enables the module.
        </Alert>
      )}

      <div className="lg:hidden">
        <StepNavigator builderStep={builderStep} stepIndex={stepIndex} onStepChange={attemptStepChange} />
      </div>

      <div className="grid gap-6 lg:grid-cols-[230px_minmax(0,1fr)]">
        <div className="hidden lg:block">
          <StepNavigator builderStep={builderStep} stepIndex={stepIndex} onStepChange={attemptStepChange} />
        </div>

        <div className="space-y-6">
          {builderError && <Alert variant="error">{builderError}</Alert>}

          <Card variant="default" className="rounded-[28px] border border-[#ffbb00]/18 bg-[linear-gradient(180deg,rgba(18,22,31,0.96),rgba(10,12,18,0.98))]">
            <CardBody className="space-y-6 p-6">
              <div className="border-b border-[#ffbb00]/12 pb-5">
                <p className="text-[11px] uppercase tracking-[0.24em] text-[#a89465]">{`Step ${stepIndex + 1} of ${BUILDER_STEPS.length}`}</p>
                <h3 className="mt-2 text-2xl font-semibold text-white">{currentStep?.title}</h3>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-[#d4c39b]">{currentStep?.description}</p>
              </div>

              {builderStep === 'details' ? (
                <DetailsStep draft={draft} updateDraft={updateDraft} computedEndTime={computedEndTime} />
              ) : null}

              {builderStep === 'connections' ? (
                <ConnectionsStep
                  draft={draft}
                  updateDraft={updateDraft}
                  eventChannelOptions={eventChannelOptions}
                  announcementChannelOptions={announcementChannelOptions}
                  signupRoleOptions={signupRoleOptions}
                  channelNameById={channelNameById}
                  eventSettings={eventSettings}
                />
              ) : null}

              {builderStep === 'review' ? (
                <ReviewStep
                  draft={draft}
                  validationError={validationError}
                  computedEndTime={computedEndTime}
                  reviewHighlights={reviewHighlights}
                  channelNameById={channelNameById}
                  roleNameById={roleNameById}
                  eventSettings={eventSettings}
                />
              ) : null}

              <div className="flex flex-col gap-3 border-t border-[#ffbb00]/12 pt-5 sm:flex-row sm:items-center sm:justify-between">
                <div className="space-y-1">
                  <p className="text-xs uppercase tracking-[0.2em] text-[#a89465]">
                    {`Step ${stepIndex + 1} of ${BUILDER_STEPS.length}`}
                  </p>
                  <p className="text-sm text-[#d4c39b]">
                    {builderStep === 'review'
                      ? 'Make sure the summary and destinations look right before posting.'
                      : currentStepError
                        ? currentStepError
                        : 'This section is ready to continue.'}
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-3">
                  <Button variant="secondary" onClick={() => navigate('/events')}>
                    Cancel
                  </Button>
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
                      {builderSaving
                        ? isEditing
                          ? 'Saving...'
                          : 'Publishing...'
                        : isEditing
                          ? 'Save Changes'
                          : 'Publish Event'}
                    </Button>
                  ) : (
                    <Button variant="success" onClick={goToNextStep} disabled={!!currentStepError}>
                      Continue
                    </Button>
                  )}
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
