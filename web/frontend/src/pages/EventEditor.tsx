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
import { Alert, Button, Card, CardBody } from '../components/ui';
import {
  BUILDER_STEPS,
  buildRecurrenceRule,
  calculateScheduledEndTime,
  combineDateAndTime,
  createDraftFromEvent,
  createEmptyDraft,
  formatLocationMode,
  getAnnouncementChannelOptions,
  getEntityTypeForLocationMode,
  getReviewHighlights,
  getStageChannelOptions,
  getVoiceChannelOptions,
  type BuilderStep,
  type EventDraft,
  validateDraft,
} from './eventFlowShared';
import { CustomStep, DetailsStep, LocationStep, ReviewStep } from './EventEditorSteps';
import { StepProgress } from './EventEditorComponents';

interface EventEditorProps {
  guildId: string;
  mode: 'create' | 'edit';
}

const STEP_SEQUENCE: BuilderStep[] = ['location', 'details', 'custom', 'review'];

function getStepValidationError(step: BuilderStep, draft: EventDraft): string | null {
  if (step === 'location') {
    if (draft.locationMode === 'external') {
      return draft.location.trim() ? null : 'Enter a location before moving on.';
    }

    return draft.channelId ? null : `Choose a ${formatLocationMode(draft.locationMode).toLowerCase()} before moving on.`;
  }

  if (step === 'details') {
    if (!draft.name.trim()) {
      return 'Add an event topic before moving on.';
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

    if (draft.locationMode === 'external' && draft.endMode === 'open') {
      return 'External events need a finish time before moving on.';
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

  if (step === 'custom') {
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
  const [builderStep, setBuilderStep] = useState<BuilderStep>('location');
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
  const stageChannelOptions = useMemo(() => getStageChannelOptions(channels), [channels]);
  const voiceChannelOptions = useMemo(() => getVoiceChannelOptions(channels), [channels]);
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

  const updateDraft = useCallback((patch: Partial<EventDraft>) => {
    setBuilderError(null);
    setDraft((currentDraft) => {
      const nextDraft = {
        ...currentDraft,
        ...patch,
      };

      if (nextDraft.locationMode === 'external' && nextDraft.endMode === 'open') {
        nextDraft.endMode = 'duration';
      }

      return nextDraft;
    });
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

      if (nextDraft.locationMode === 'voice') {
        if (!nextDraft.channelId || !voiceChannelOptions.some((option) => option.id === nextDraft.channelId)) {
          nextDraft.channelId = eventSettings?.default_voice_channel_id ?? voiceChannelOptions[0]?.id ?? null;
        }
      } else if (nextDraft.locationMode === 'stage') {
        if (!nextDraft.channelId || !stageChannelOptions.some((option) => option.id === nextDraft.channelId)) {
          nextDraft.channelId = stageChannelOptions[0]?.id ?? null;
        }
      } else {
        nextDraft.channelId = null;
        if (nextDraft.endMode === 'open') {
          nextDraft.endMode = 'duration';
        }
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
  }, [announcementChannelOptions, eventSettings, loading, stageChannelOptions, voiceChannelOptions]);

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
    if (builderStep === 'location') {
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

      if (getStepValidationError('location', draft)) {
        setBuilderStep('location');
      } else if (getStepValidationError('details', draft)) {
        setBuilderStep('details');
      } else if (getStepValidationError('custom', draft)) {
        setBuilderStep('custom');
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
        entity_type: getEntityTypeForLocationMode(draft.locationMode),
        channel_id: draft.locationMode === 'external' ? null : draft.channelId,
        location: draft.locationMode === 'external' ? draft.location.trim() : null,
        announcement_channel_id: draft.announcementChannelId,
        signup_role_ids: draft.signupRoleIds ?? [],
        recurrence_rule: buildRecurrenceRule(draft),
        image_data: draft.imageData,
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
    <div className="mx-auto max-w-3xl space-y-4 py-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-[#c8c9d0]">{guildInfo?.guild_name || 'Current guild'}</p>
          <h1 className="text-2xl font-bold text-[#fff4cc]">{isEditing ? 'Edit event' : 'Create event'}</h1>
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

      <Card variant="default" className="rounded-xl border border-[#ffbb00]/18 bg-[linear-gradient(180deg,rgba(18,13,0,0.96),rgba(7,7,7,0.98))] text-[#f5deb3] shadow-2xl shadow-black/35">
        <CardBody className="space-y-7 p-6 sm:p-8">
          <StepProgress builderStep={builderStep} stepIndex={stepIndex} onStepChange={attemptStepChange} />

          {builderError && <Alert variant="error">{builderError}</Alert>}

          {builderStep === 'location' ? (
            <LocationStep
              draft={draft}
              updateDraft={updateDraft}
              stageChannelOptions={stageChannelOptions}
              voiceChannelOptions={voiceChannelOptions}
            />
          ) : null}

          {builderStep === 'details' ? (
            <DetailsStep draft={draft} updateDraft={updateDraft} computedEndTime={computedEndTime} />
          ) : null}

          {builderStep === 'custom' ? (
            <CustomStep
              draft={draft}
              updateDraft={updateDraft}
              announcementChannelOptions={announcementChannelOptions}
              signupRoleOptions={signupRoleOptions}
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
            />
          ) : null}

          <div className="flex flex-col gap-4 pt-2 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm leading-6 text-[#d4c39b]">
              {builderStep === 'review'
                ? 'Make sure the preview looks right before posting.'
                : currentStepError
                  ? currentStepError
                  : currentStep?.description}
            </p>

            <div className="flex flex-wrap items-center justify-end gap-3">
              {builderStep !== 'location' ? (
                <Button variant="secondary" onClick={goToPreviousStep}>
                  Back
                </Button>
              ) : null}
              <Button variant="secondary" onClick={() => navigate('/events')}>
                Cancel
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
                      : 'Creating...'
                    : isEditing
                      ? 'Save Changes'
                      : 'Create Event'}
                </Button>
              ) : (
                <Button variant="success" onClick={goToNextStep} disabled={!!currentStepError}>
                  Next
                </Button>
              )}
            </div>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

export default EventEditor;
