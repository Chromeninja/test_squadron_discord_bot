import { useState } from 'react';

import SearchableSelect from '../components/SearchableSelect';
import { Alert, Input, Textarea } from '../components/ui';
import { inputVariants } from '../utils/theme';
import {
  DURATION_OPTIONS,
  RECURRENCE_FREQUENCY_OPTIONS,
  RECURRENCE_WEEKDAY_OPTIONS,
  combineDateAndTime,
  formatDuration,
  formatEventDate,
  formatLocationMode,
  formatRecurrenceSummary,
  type EndMode,
  type EventDraft,
  type EventLocationMode,
  type RecurrenceFrequency,
  type RecurrenceWeekday,
} from './eventFlowShared';
import { ReviewRow, getOptionButtonClass } from './EventEditorComponents';

type SelectOption = Array<{ id: string; name: string; category?: string }>;
type DraftUpdater = (patch: Partial<EventDraft>) => void;

const EVENT_IMAGE_MAX_BYTES = 8 * 1024 * 1024;

function formatFileSize(bytes: number | null): string {
  if (bytes === null) {
    return 'Stored by Discord';
  }

  return `${(bytes / (1024 * 1024)).toFixed(2)} MiB`;
}

function readImageAsDataUri(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener('load', () => {
      if (typeof reader.result === 'string') {
        resolve(reader.result);
        return;
      }
      reject(new Error('Image data could not be read.'));
    });
    reader.addEventListener('error', () => reject(new Error('Image data could not be read.')));
    reader.readAsDataURL(file);
  });
}

function getSelectedLocationName(draft: EventDraft, channelNameById: Map<string, string>): string {
  if (draft.locationMode === 'external') {
    return draft.location.trim() || 'No location entered';
  }

  return draft.channelId
    ? channelNameById.get(draft.channelId) || 'Configured channel'
    : `No ${formatLocationMode(draft.locationMode).toLowerCase()} selected`;
}

interface LocationStepProps {
  draft: EventDraft;
  updateDraft: DraftUpdater;
  stageChannelOptions: SelectOption;
  voiceChannelOptions: SelectOption;
}

export function LocationStep({ draft, updateDraft, stageChannelOptions, voiceChannelOptions }: LocationStepProps) {
  const locationOptions: Array<{ id: EventLocationMode; title: string; description: string }> = [
    { id: 'stage', title: 'Stage Channel', description: 'Great for larger community audio events.' },
    { id: 'voice', title: 'Voice Channel', description: 'Hang out with voice, video, screenshare, and Go Live.' },
    { id: 'external', title: 'Somewhere Else', description: 'Text channel, external link, or in-person location.' },
  ];
  const getDefaultChannelId = (mode: EventLocationMode): string | null => {
    if (mode === 'voice') {
      return voiceChannelOptions[0]?.id ?? null;
    }
    if (mode === 'stage') {
      return stageChannelOptions[0]?.id ?? null;
    }
    return null;
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-[#fff4cc]">Where is your event?</h2>
        <p className="mt-2 text-sm leading-6 text-[#d4c39b]">So no one gets lost on where to go.</p>
      </div>

      <div className="space-y-3">
        {locationOptions.map((option) => {
          const isSelected = draft.locationMode === option.id;
          return (
            <button
              key={option.id}
              type="button"
              onClick={() => updateDraft({ locationMode: option.id, channelId: isSelected ? draft.channelId : getDefaultChannelId(option.id) })}
              className="flex w-full items-start gap-4 rounded-lg border border-transparent px-3 py-3 text-left transition hover:border-[#ffbb00]/18 hover:bg-[#ffbb00]/8"
            >
              <span className={['mt-1 flex h-7 w-7 flex-none items-center justify-center rounded-full border-2', isSelected ? 'border-[#ffbb00] bg-[#ffbb00]/20' : 'border-[#a89465]'].join(' ')}>
                {isSelected ? <span className="h-2.5 w-2.5 rounded-full bg-[#ffdd73]" /> : null}
              </span>
              <span>
                <span className="block text-lg font-semibold text-[#fff4cc]">{option.title}</span>
                <span className="mt-1 block text-sm leading-6 text-[#d4c39b]">{option.description}</span>
              </span>
            </button>
          );
        })}
      </div>

      {draft.locationMode === 'stage' ? (
        <div>
          <label className="mb-2 block text-sm font-semibold text-[#fff4cc]">Select a stage channel</label>
          <SearchableSelect options={stageChannelOptions} selected={draft.channelId} onChange={(value) => updateDraft({ channelId: value })} placeholder="Choose a stage channel" />
        </div>
      ) : null}

      {draft.locationMode === 'voice' ? (
        <div>
          <label className="mb-2 block text-sm font-semibold text-[#fff4cc]">Select a voice channel</label>
          <SearchableSelect options={voiceChannelOptions} selected={draft.channelId} onChange={(value) => updateDraft({ channelId: value })} placeholder="Choose a voice channel" />
        </div>
      ) : null}

      {draft.locationMode === 'external' ? (
        <Input label="Enter a location" required value={draft.location} onChange={(event) => updateDraft({ location: event.target.value })} placeholder="Paste a link, channel name, or meetup location" />
      ) : null}
    </div>
  );
}

interface DetailsStepProps {
  draft: EventDraft;
  updateDraft: DraftUpdater;
  computedEndTime: string | null;
}

export function DetailsStep({ draft, updateDraft, computedEndTime }: DetailsStepProps) {
  const [imageError, setImageError] = useState<string | null>(null);
  const endModeOptions =
    draft.locationMode === 'external'
      ? [
          { id: 'duration', label: 'Use duration' },
          { id: 'manual', label: 'Set end time' },
        ]
      : [
          { id: 'duration', label: 'Use duration' },
          { id: 'manual', label: 'Set end time' },
          { id: 'open', label: 'Open-ended' },
        ];

  const handleImageChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) {
      return;
    }
    if (!['image/png', 'image/jpeg'].includes(file.type)) {
      setImageError('Use a PNG or JPEG image for Discord event covers.');
      return;
    }
    if (file.size > EVENT_IMAGE_MAX_BYTES) {
      setImageError('Event cover images must be 8 MiB or smaller.');
      return;
    }

    try {
      const imageData = await readImageAsDataUri(file);
      setImageError(null);
      updateDraft({ imageData, imagePreviewUrl: imageData, imageName: file.name, imageSize: file.size });
    } catch {
      setImageError('Could not read that image. Try a different PNG or JPEG.');
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-[#fff4cc]">What's your event about?</h2>
        <p className="mt-2 text-sm leading-6 text-[#d4c39b]">Fill out the details of your event.</p>
      </div>

      <Input label="Event Topic" required value={draft.name} onChange={(event) => updateDraft({ name: event.target.value })} placeholder="What's your event?" />

      <div className="grid gap-4 sm:grid-cols-2">
        <Input id="start-date" label="Start Date" required type="date" value={draft.startDate} onChange={(event) => updateDraft({ startDate: event.target.value })} />
        <Input id="start-time" label="Start Time" required type="time" step={60} value={draft.startTime} onChange={(event) => updateDraft({ startTime: event.target.value })} />
      </div>

      <div className="space-y-3">
        <div className="flex flex-wrap gap-2">
          {endModeOptions.map((option) => (
            <button key={option.id} type="button" onClick={() => updateDraft({ endMode: option.id as EndMode })} className={getOptionButtonClass(draft.endMode === option.id)}>
              {option.label}
            </button>
          ))}
        </div>

        {draft.endMode === 'duration' ? (
          <div className="space-y-3 rounded-lg border border-[#ffbb00]/15 bg-[#120d00] p-4">
            <div className="flex flex-wrap gap-2">
              {DURATION_OPTIONS.map((option) => (
                <button key={option.value} type="button" onClick={() => updateDraft({ durationMinutes: option.value })} className={getOptionButtonClass(draft.durationMinutes === option.value, 'compact')}>
                  {option.label}
                </button>
              ))}
            </div>
            <Input label="Custom Duration (minutes)" type="number" min={15} step={15} value={draft.durationMinutes} onChange={(event) => updateDraft({ durationMinutes: event.target.value })} helperText={`Current finish plan: ${formatDuration(draft.durationMinutes)}`} />
          </div>
        ) : null}

        {draft.endMode === 'manual' ? (
          <div className="grid gap-4 rounded-lg border border-[#ffbb00]/15 bg-[#120d00] p-4 sm:grid-cols-2">
            <Input id="end-date" label="End Date" type="date" value={draft.endDate} onChange={(event) => updateDraft({ endDate: event.target.value })} />
            <Input id="end-time" label="End Time" type="time" step={60} value={draft.endTime} onChange={(event) => updateDraft({ endTime: event.target.value })} helperText={`Current finish plan: ${formatEventDate(computedEndTime)}`} />
          </div>
        ) : null}
      </div>

      <div>
        <label className="mb-2 block text-sm font-semibold text-[#fff4cc]">Event Frequency</label>
        <button type="button" onClick={() => updateDraft({ recurrenceEnabled: !draft.recurrenceEnabled })} className={getOptionButtonClass(draft.recurrenceEnabled)}>
          {draft.recurrenceEnabled ? 'Repeats' : 'Does not repeat'}
        </button>
      </div>

      {draft.recurrenceEnabled ? (
        <div className="space-y-4 rounded-lg border border-[#ffbb00]/15 bg-[#120d00] p-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm font-medium text-[#d4c39b]">Frequency</label>
              <select value={draft.recurrenceFrequency} onChange={(event) => updateDraft({ recurrenceFrequency: Number(event.target.value) as RecurrenceFrequency })} className={inputVariants.base}>
                {RECURRENCE_FREQUENCY_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </div>
            <Input label="Interval" type="number" min={1} step={1} value={draft.recurrenceInterval} onChange={(event) => updateDraft({ recurrenceInterval: event.target.value })} />
          </div>

          {draft.recurrenceFrequency === 2 ? (
            <div className="space-y-2">
              <p className="text-sm font-medium text-[#d4c39b]">Weekdays</p>
              <div className="flex flex-wrap gap-2">
                {RECURRENCE_WEEKDAY_OPTIONS.map((option) => {
                  const isSelected = draft.recurrenceWeekdays.includes(option.value);
                  return (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => {
                        const nextWeekdays = isSelected ? draft.recurrenceWeekdays.filter((day) => day !== option.value) : [...draft.recurrenceWeekdays, option.value];
                        updateDraft({ recurrenceWeekdays: [...nextWeekdays].sort((a, b) => a - b) as RecurrenceWeekday[] });
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

          <p className="text-sm text-[#d4c39b]">{formatRecurrenceSummary(draft)}</p>
        </div>
      ) : null}

      <Textarea
        label="Description"
        value={draft.description}
        onChange={(event) => {
          const nextDescription = event.target.value;
          updateDraft(draft.announcementMessage.trim() ? { description: nextDescription } : { description: nextDescription, announcementMessage: nextDescription });
        }}
        placeholder="Tell people a little more about your event. Markdown, new lines, and links are supported."
      />

      <div className="space-y-3">
        <div>
          <label className="block text-sm font-semibold text-[#fff4cc]" htmlFor="event-cover-image">Cover Image</label>
          <p className="mt-1 text-sm text-[#d4c39b]">We recommend an image that's at least 800px wide and 320px tall.</p>
        </div>
        {draft.imagePreviewUrl ? <img src={draft.imagePreviewUrl} alt="Event cover preview" className="aspect-video w-full rounded-lg border border-[#ffbb00]/15 object-cover" /> : null}
        <input id="event-cover-image" type="file" accept="image/png,image/jpeg,.png,.jpg,.jpeg" onChange={(event) => { void handleImageChange(event); }} className={inputVariants.base} />
        {draft.imageName ? <p className="text-xs leading-5 text-[#d4c39b]">{draft.imageName} - {formatFileSize(draft.imageSize)}</p> : null}
        {imageError ? <p className="text-sm text-red-300">{imageError}</p> : null}
      </div>
    </div>
  );
}

interface CustomStepProps {
  draft: EventDraft;
  updateDraft: DraftUpdater;
  announcementChannelOptions: SelectOption;
}

export function CustomStep({ draft, updateDraft, announcementChannelOptions }: CustomStepProps) {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-[#fff4cc]">Bot options</h2>
        <p className="mt-2 text-sm leading-6 text-[#d4c39b]">Add the extras Discord does not manage for us.</p>
      </div>

      <div>
        <label className="mb-2 block text-sm font-semibold text-[#fff4cc]">Announcement Channel</label>
        <SearchableSelect options={announcementChannelOptions} selected={draft.announcementChannelId} onChange={(value) => updateDraft({ announcementChannelId: value })} placeholder="Choose a text channel" />
      </div>

      <Textarea label="Announcement Message" value={draft.announcementMessage} onChange={(event) => updateDraft({ announcementMessage: event.target.value })} placeholder="Defaults to the event description. Keep it short if the event brief already has the details." />
    </div>
  );
}

interface ReviewStepProps {
  draft: EventDraft;
  validationError: string | null;
  computedEndTime: string | null;
  reviewHighlights: string[];
  channelNameById: Map<string, string>;
}

export function ReviewStep({ draft, validationError, computedEndTime, reviewHighlights, channelNameById }: ReviewStepProps) {
  return (
    <div className="space-y-6">
      {validationError ? <Alert variant="warning">{validationError}</Alert> : null}

      <div>
        <h2 className="text-2xl font-bold text-[#fff4cc]">Here's a preview of your event.</h2>
        <p className="mt-2 text-sm leading-6 text-[#d4c39b]">This event will auto start when it's time.</p>
      </div>

      <div className="overflow-hidden rounded-lg border border-[#ffbb00]/18 bg-[#120d00]">
        {draft.imagePreviewUrl ? <img src={draft.imagePreviewUrl} alt="Event cover preview" className="aspect-[2.5/1] w-full object-cover" /> : null}
        <div className="space-y-4 p-5">
          <div className="flex flex-wrap items-center gap-3 text-sm font-semibold text-[#ffdd73]">
            <span>{draft.startDate && draft.startTime ? formatEventDate(combineDateAndTime(draft.startDate, draft.startTime)) : 'Start time not set'}</span>
            <span className="rounded-full border border-[#ffbb00]/18 bg-[#ffbb00]/10 px-3 py-1 text-[#fff1bf]">0 interested</span>
          </div>
          <div>
            <h3 className="text-xl font-bold text-[#fff4cc]">{draft.name || 'Untitled event'}</h3>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-[#d4c39b]">{draft.description || 'No description added.'}</p>
          </div>
          <div className="border-t border-[#ffbb00]/15 pt-4 text-base font-semibold text-[#f5deb3]">{getSelectedLocationName(draft, channelNameById)}</div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-3 rounded-lg border border-[#ffbb00]/15 bg-[#120d00] p-4 text-sm">
          <p className="text-[11px] uppercase tracking-[0.24em] text-[#ffbb00]/70">Discord event</p>
          <ReviewRow label="Type" value={formatLocationMode(draft.locationMode)} />
          <ReviewRow label="Starts" value={draft.startDate && draft.startTime ? formatEventDate(combineDateAndTime(draft.startDate, draft.startTime)) : 'Not set'} />
          <ReviewRow label="Ends" value={formatEventDate(computedEndTime)} />
          <ReviewRow label="Recurrence" value={formatRecurrenceSummary(draft)} />
          <ReviewRow label="Cover image" value={draft.imagePreviewUrl ? draft.imageName || 'Discord cover selected' : 'None'} />
        </div>

        <div className="space-y-3 rounded-lg border border-[#ffbb00]/15 bg-[#120d00] p-4 text-sm">
          <p className="text-[11px] uppercase tracking-[0.24em] text-[#ffbb00]/70">Bot options</p>
          <ReviewRow label="Announcement channel" value={draft.announcementChannelId ? channelNameById.get(draft.announcementChannelId) || 'Configured channel' : 'Not set'} />
          <ReviewRow label="Announcement message" value={draft.announcementMessage.trim() || draft.description.trim() || 'Default summary'} multiLine />
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {reviewHighlights.map((highlight) => <span key={highlight} className="rounded-full border border-[#ffbb00]/18 bg-[#ffbb00]/10 px-3 py-1 text-xs font-semibold text-[#fff1bf]">{highlight}</span>)}
      </div>
    </div>
  );
}
