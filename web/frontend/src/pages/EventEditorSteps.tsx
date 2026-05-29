import SearchableSelect from '../components/SearchableSelect';
import SearchableMultiSelect from '../components/SearchableMultiSelect';
import { Alert, Card, CardBody, Input, Textarea } from '../components/ui';
import { inputVariants } from '../utils/theme';
import type { EventModuleSettingsPayload } from '../api/endpoints';
import {
  DURATION_OPTIONS,
  RECURRENCE_FREQUENCY_OPTIONS,
  RECURRENCE_WEEKDAY_OPTIONS,
  combineDateAndTime,
  formatDuration,
  formatEventDate,
  formatRecurrenceSummary,
  type EndMode,
  type EventDraft,
  type RecurrenceFrequency,
  type RecurrenceWeekday,
} from './eventFlowShared';
import {
  CompactSummaryCard,
  EventSection,
  ReviewRow,
  getOptionButtonClass,
} from './EventEditorComponents';

type SelectOption = Array<{ id: string; name: string; category?: string }>;
type RoleOption = Array<{ id: string; name: string }>;
type DraftUpdater = (patch: Partial<EventDraft>) => void;

interface DetailsStepProps {
  draft: EventDraft;
  updateDraft: DraftUpdater;
  computedEndTime: string | null;
}

export function DetailsStep({ draft, updateDraft, computedEndTime }: DetailsStepProps) {
  return (
    <div className="space-y-6">
      <EventSection
        eyebrow="Primary details"
        title="What is this event?"
        description="Lead with the name and mission brief so the preview reads well before you worry about routing and audience settings."
      >
        <Input
          label="Event Name"
          value={draft.name}
          onChange={(event) => updateDraft({ name: event.target.value })}
          placeholder="e.g. Fleet Night"
          helperText="Use the short name members will recognize in the events list."
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
                  }
            );
          }}
          placeholder="Add the mission brief, prep notes, or agenda"
        />
      </EventSection>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
        <EventSection
          eyebrow="Schedule"
          title="When does it start?"
          description="Set the anchor date and start time first. The finish strategy can stay lightweight until the plan is firm."
        >
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
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
        </EventSection>

        <EventSection
          eyebrow="Finish"
          title="How should it end?"
          description="Pick the least complex finish rule that still communicates the plan clearly."
        >
          <div className="flex flex-wrap gap-2">
            {[
              { id: 'duration', label: 'Use duration' },
              { id: 'manual', label: 'Set end time' },
              { id: 'open', label: 'Open-ended' },
            ].map((option) => (
              <button
                key={option.id}
                type="button"
                onClick={() => updateDraft({ endMode: option.id as EndMode })}
                className={getOptionButtonClass(draft.endMode === option.id)}
              >
                {option.label}
              </button>
            ))}
          </div>

          {draft.endMode === 'duration' ? (
            <div className="space-y-3">
              <div className="flex flex-wrap gap-2">
                {DURATION_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => updateDraft({ durationMinutes: option.value })}
                    className={getOptionButtonClass(draft.durationMinutes === option.value, 'compact')}
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
          ) : null}

          {draft.endMode === 'manual' ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
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
          ) : null}

          <div className="rounded-2xl border border-slate-800 bg-black/25 px-4 py-3 text-sm text-slate-400">
            {draft.endMode === 'duration'
              ? `Current finish plan: ${formatDuration(draft.durationMinutes)}`
              : draft.endMode === 'manual'
                ? `Current finish plan: ${formatEventDate(computedEndTime)}`
                : 'Current finish plan: open-ended.'}
          </div>
        </EventSection>
      </div>

      <Card variant="ghost" className="border border-dashed border-slate-800 bg-black/20">
        <CardBody className="space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="text-[11px] uppercase tracking-[0.24em] text-slate-500">Optional cadence</p>
              <h4 className="mt-2 text-base font-semibold text-white">Recurrence</h4>
              <p className="mt-1 max-w-2xl text-sm leading-6 text-slate-400">
                Only turn this on when members truly need a repeating schedule. For one-off operations, keeping it disabled usually reads better.
              </p>
            </div>
            <button
              type="button"
              onClick={() => updateDraft({ recurrenceEnabled: !draft.recurrenceEnabled })}
              className={getOptionButtonClass(draft.recurrenceEnabled)}
            >
              {draft.recurrenceEnabled ? 'Enabled' : 'Disabled'}
            </button>
          </div>

          {draft.recurrenceEnabled ? (
            <div className="space-y-4 rounded-2xl border border-[#ffbb00]/15 bg-[#0f0b00]/60 p-4">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="space-y-1">
                  <label className="block text-sm font-medium text-gray-300">Frequency</label>
                  <select
                    value={draft.recurrenceFrequency}
                    onChange={(event) =>
                      updateDraft({
                        recurrenceFrequency: Number(event.target.value) as RecurrenceFrequency,
                      })
                    }
                    className={inputVariants.base}
                  >
                    {RECURRENCE_FREQUENCY_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>
                <Input
                  label="Interval"
                  type="number"
                  min={1}
                  step={1}
                  value={draft.recurrenceInterval}
                  onChange={(event) => updateDraft({ recurrenceInterval: event.target.value })}
                />
              </div>

              {draft.recurrenceFrequency === 2 ? (
                <div className="space-y-2">
                  <p className="text-sm font-medium text-gray-300">Weekdays</p>
                  <div className="flex flex-wrap gap-2">
                    {RECURRENCE_WEEKDAY_OPTIONS.map((option) => {
                      const isSelected = draft.recurrenceWeekdays.includes(option.value);
                      return (
                        <button
                          key={option.value}
                          type="button"
                          onClick={() => {
                            const nextWeekdays = isSelected
                              ? draft.recurrenceWeekdays.filter((day) => day !== option.value)
                              : [...draft.recurrenceWeekdays, option.value];
                            updateDraft({
                              recurrenceWeekdays: [...nextWeekdays].sort((a, b) => a - b) as RecurrenceWeekday[],
                            });
                          }}
                          className={getOptionButtonClass(isSelected, 'compact')}
                        >
                          {option.label}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ) : null}

              <p className="text-xs leading-5 text-slate-400">{formatRecurrenceSummary(draft)}</p>
            </div>
          ) : null}
        </CardBody>
      </Card>
    </div>
  );
}

interface ConnectionsStepProps {
  draft: EventDraft;
  updateDraft: DraftUpdater;
  eventChannelOptions: SelectOption;
  announcementChannelOptions: SelectOption;
  signupRoleOptions: RoleOption;
  channelNameById: Map<string, string>;
  eventSettings: EventModuleSettingsPayload | null;
}

export function ConnectionsStep({
  draft,
  updateDraft,
  eventChannelOptions,
  announcementChannelOptions,
  signupRoleOptions,
  channelNameById,
  eventSettings,
}: ConnectionsStepProps) {
  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,0.95fr)]">
      <EventSection
        eyebrow="Destinations"
        title="Where should this live?"
        description="Choose the live voice destination and the announcement channel together so the routing is easy to confirm at a glance."
      >
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-300">Event Channel</label>
          <SearchableSelect
            options={eventChannelOptions}
            selected={draft.channelId}
            onChange={(value) => updateDraft({ channelId: value })}
            placeholder="Choose a voice channel"
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-gray-300">Announcement Channel</label>
          <SearchableSelect
            options={announcementChannelOptions}
            selected={draft.announcementChannelId}
            onChange={(value) => updateDraft({ announcementChannelId: value })}
            placeholder="Choose a text channel"
          />
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <CompactSummaryCard
            label="Event Channel"
            value={
              draft.channelId
                ? channelNameById.get(draft.channelId) || 'Configured voice channel'
                : 'No voice channel selected'
            }
          />
          <CompactSummaryCard
            label="Announcement Channel"
            value={
              draft.announcementChannelId
                ? channelNameById.get(draft.announcementChannelId) || 'Configured channel'
                : 'No announcement channel selected'
            }
          />
        </div>
      </EventSection>

      <EventSection
        eyebrow="Audience"
        title="What should members see?"
        description="Use signup roles and the announcement message only where they make the post more useful."
      >
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

        <Card variant="ghost" className="border border-slate-800 bg-black/20">
          <CardBody className="space-y-2">
            <p className="text-[11px] uppercase tracking-[0.24em] text-slate-500">Publishing posture</p>
            <p className="text-sm text-slate-200">
              {eventSettings?.default_native_sync === false
                ? 'This guild is set to a manual coordinator sync posture.'
                : 'This guild will use the native Discord event sync by default.'}
            </p>
            <p className="text-xs leading-5 text-slate-400">
              Keep the announcement message concise when the description already carries the full mission brief.
            </p>
          </CardBody>
        </Card>
      </EventSection>
    </div>
  );
}

interface ReviewStepProps {
  draft: EventDraft;
  validationError: string | null;
  computedEndTime: string | null;
  reviewHighlights: string[];
  channelNameById: Map<string, string>;
  roleNameById: Map<string, string>;
  eventSettings: EventModuleSettingsPayload | null;
}

export function ReviewStep({
  draft,
  validationError,
  computedEndTime,
  reviewHighlights,
  channelNameById,
  roleNameById,
  eventSettings,
}: ReviewStepProps) {
  return (
    <div className="space-y-5">
      {validationError ? <Alert variant="warning">{validationError}</Alert> : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
        <Card variant="default">
          <CardBody className="space-y-4">
            <div>
              <p className="text-[11px] uppercase tracking-[0.24em] text-[#a89465]">Review before publish</p>
              <h4 className="mt-2 text-lg font-semibold text-[#fff4cc]">
                {draft.name || 'Untitled event'}
              </h4>
              <p className="mt-2 text-sm leading-6 text-[#d4c39b]">
                Check the final member-facing details and the routing choices below before posting.
              </p>
            </div>

            <div className="space-y-3 rounded-2xl border border-[#ffbb00]/12 bg-black/20 p-4">
              <ReviewRow label="Type" value="Voice event" />
              <ReviewRow
                label="Starts"
                value={
                  draft.startDate && draft.startTime
                    ? formatEventDate(combineDateAndTime(draft.startDate, draft.startTime))
                    : 'Not set'
                }
              />
              <ReviewRow label="Ends" value={formatEventDate(computedEndTime)} />
              <ReviewRow label="Recurrence" value={formatRecurrenceSummary(draft)} />
              <ReviewRow
                label="Voice destination"
                value={
                  draft.channelId
                    ? channelNameById.get(draft.channelId) || 'Configured voice channel'
                    : 'No voice channel selected'
                }
              />
              <ReviewRow
                label="Announcement channel"
                value={
                  draft.announcementChannelId
                    ? channelNameById.get(draft.announcementChannelId) || 'Configured channel'
                    : 'Not set'
                }
              />
              <ReviewRow
                label="Signup roles"
                value={
                  (draft.signupRoleIds ?? []).length > 0
                    ? (draft.signupRoleIds ?? [])
                        .map((roleId) => roleNameById.get(roleId) || `Role ${roleId}`)
                        .join(', ')
                    : 'None'
                }
              />
              <ReviewRow
                label="Announcement message"
                value={draft.announcementMessage.trim() || draft.description.trim() || 'Default summary'}
                multiLine
              />
            </div>
          </CardBody>
        </Card>

        <Card variant="default">
          <CardBody className="space-y-4">
            <div>
              <p className="text-[11px] uppercase tracking-[0.24em] text-[#a89465]">Operator summary</p>
              <h4 className="mt-2 text-lg font-semibold text-[#fff4cc]">What stands out</h4>
            </div>

            <div className="flex flex-wrap gap-2">
              {reviewHighlights.map((highlight) => (
                <span
                  key={highlight}
                  className="rounded-full border border-[#ffbb00]/18 bg-[#ffbb00]/10 px-3 py-1 text-xs font-medium text-[#fff1bf]"
                >
                  {highlight}
                </span>
              ))}
            </div>

            <div className="space-y-3 rounded-2xl border border-[#ffbb00]/12 bg-black/20 p-4 text-sm leading-6 text-[#d4c39b]">
              <p>
                <span className="font-medium text-[#fff4cc]">Member preview:</span>{' '}
                {draft.description || 'No mission brief added yet.'}
              </p>
              <p>
                <span className="font-medium text-[#fff4cc]">Post destination:</span>{' '}
                {draft.announcementChannelId
                  ? channelNameById.get(draft.announcementChannelId) || 'Configured channel'
                  : 'No announcement channel selected'}
              </p>
              <p>
                <span className="font-medium text-[#fff4cc]">Sync posture:</span>{' '}
                {eventSettings?.default_native_sync === false
                  ? 'Manual coordinator sync posture'
                  : 'Native Discord sync enabled'}
              </p>
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

