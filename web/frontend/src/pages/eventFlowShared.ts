import {
  type DiscordChannel,
  type EventModuleSettingsPayload,
  type ScheduledEventCreateRequest,
  type ScheduledEventSummary,
} from '../api/endpoints';
import { type BadgeVariant } from '../utils/theme';

export type BuilderStep = 'details' | 'connections' | 'review';
export type EndMode = 'duration' | 'manual' | 'open';
export type RecurrenceFrequency = 0 | 1 | 2 | 3;
export type RecurrenceWeekday = 0 | 1 | 2 | 3 | 4 | 5 | 6;

export const RECURRENCE_WEEKDAY_OPTIONS: Array<{ value: RecurrenceWeekday; label: string }> = [
  { value: 0, label: 'Mon' },
  { value: 1, label: 'Tue' },
  { value: 2, label: 'Wed' },
  { value: 3, label: 'Thu' },
  { value: 4, label: 'Fri' },
  { value: 5, label: 'Sat' },
  { value: 6, label: 'Sun' },
];

export const RECURRENCE_FREQUENCY_OPTIONS: Array<{
  value: RecurrenceFrequency;
  label: string;
}> = [
  { value: 3, label: 'Daily' },
  { value: 2, label: 'Weekly' },
  { value: 1, label: 'Monthly' },
  { value: 0, label: 'Yearly' },
];

export interface EventDraft {
  name: string;
  description: string;
  announcementMessage: string;
  channelId: string | null;
  startDate: string;
  startTime: string;
  endMode: EndMode;
  durationMinutes: string;
  endDate: string;
  endTime: string;
  announcementChannelId: string | null;
  signupRoleIds: string[];
  recurrenceEnabled: boolean;
  recurrenceFrequency: RecurrenceFrequency;
  recurrenceInterval: string;
  recurrenceWeekdays: RecurrenceWeekday[];
}

export const BUILDER_STEPS: Array<{
  id: BuilderStep;
  title: string;
  description: string;
}> = [
  {
    id: 'details',
    title: 'Event details',
    description: 'Core schedule, type, and presentation.',
  },
  {
    id: 'connections',
    title: 'Connections',
    description: 'Channels and announcements.',
  },
  {
    id: 'review',
    title: 'Review & publish',
    description: 'Confirm the event before syncing.',
  },
];

export const DURATION_OPTIONS = [
  { value: '30', label: '30 min' },
  { value: '60', label: '1 hour' },
  { value: '90', label: '90 min' },
  { value: '120', label: '2 hours' },
  { value: '180', label: '3 hours' },
];

export function combineDateAndTime(date: string, time: string): string {
  return new Date(`${date}T${time}`).toISOString();
}

export function splitDateAndTime(value: string | null): { date: string; time: string } {
  if (!value) {
    return { date: '', time: '' };
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return { date: '', time: '' };
  }

  const year = parsed.getFullYear();
  const month = `${parsed.getMonth() + 1}`.padStart(2, '0');
  const day = `${parsed.getDate()}`.padStart(2, '0');
  const hours = `${parsed.getHours()}`.padStart(2, '0');
  const minutes = `${parsed.getMinutes()}`.padStart(2, '0');

  return {
    date: `${year}-${month}-${day}`,
    time: `${hours}:${minutes}`,
  };
}

export function formatEventDate(value: string | null): string {
  if (!value) {
    return 'Not scheduled';
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return 'Invalid date';
  }

  return parsed.toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

export function getStatusTone(status: string): BadgeVariant {
  switch (status) {
    case 'active':
      return 'success';
    case 'completed':
      return 'neutral';
    case 'cancelled':
    case 'canceled':
      return 'error';
    default:
      return 'info';
  }
}

export function createEmptyDraft(settings: EventModuleSettingsPayload | null): EventDraft {
  return {
    name: '',
    description: '',
    announcementMessage: '',
    channelId: settings?.default_voice_channel_id ?? null,
    startDate: '',
    startTime: '',
    endMode: 'duration',
    durationMinutes: '120',
    endDate: '',
    endTime: '',
    announcementChannelId: settings?.default_announcement_channel_id ?? null,
    signupRoleIds: [],
    recurrenceEnabled: false,
    recurrenceFrequency: 2,
    recurrenceInterval: '1',
    recurrenceWeekdays: [],
  };
}

export function createDraftFromEvent(
  event: ScheduledEventSummary,
  settings: EventModuleSettingsPayload | null,
): EventDraft {
  const start = splitDateAndTime(event.scheduled_start_time);
  const end = splitDateAndTime(event.scheduled_end_time);
  const startTime = event.scheduled_start_time ? new Date(event.scheduled_start_time) : null;
  const endTime = event.scheduled_end_time ? new Date(event.scheduled_end_time) : null;
  const durationMinutes =
    startTime && endTime && endTime.getTime() > startTime.getTime()
      ? String(Math.round((endTime.getTime() - startTime.getTime()) / 60000))
      : '120';
  const recurrencePayload = event.recurrence_rule_payload;

  return {
    name: event.name,
    description: event.description ?? '',
    announcementMessage: event.description ?? '',
    channelId: event.channel_id ?? settings?.default_voice_channel_id ?? null,
    startDate: start.date,
    startTime: start.time,
    endMode: event.scheduled_end_time ? 'manual' : 'open',
    durationMinutes,
    endDate: end.date,
    endTime: end.time,
    announcementChannelId: settings?.default_announcement_channel_id ?? null,
    signupRoleIds: [],
    recurrenceEnabled: !!recurrencePayload,
    recurrenceFrequency: recurrencePayload?.frequency ?? 2,
    recurrenceInterval: String(recurrencePayload?.interval ?? 1),
    recurrenceWeekdays: (recurrencePayload?.by_weekday ?? []).filter(
      (day): day is RecurrenceWeekday => Number.isInteger(day) && day >= 0 && day <= 6,
    ),
  };
}

export function formatDuration(minutesValue: string): string {
  const minutes = Number(minutesValue);
  if (!Number.isFinite(minutes) || minutes <= 0) {
    return 'Open-ended';
  }

  if (minutes % 60 === 0) {
    const hours = minutes / 60;
    return `${hours} hour${hours === 1 ? '' : 's'}`;
  }

  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;

  if (hours === 0) {
    return `${remainder} min`;
  }

  return `${hours}h ${remainder}m`;
}

export function formatRecurrenceSummary(draft: EventDraft): string {
  if (!draft.recurrenceEnabled) {
    return 'One-time event';
  }

  const intervalRaw = Number(draft.recurrenceInterval);
  const interval = Number.isFinite(intervalRaw) && intervalRaw > 0 ? intervalRaw : 1;
  const baseLabel =
    RECURRENCE_FREQUENCY_OPTIONS.find((item) => item.value === draft.recurrenceFrequency)
      ?.label ?? 'Recurring';

  const prefix =
    interval === 1
      ? baseLabel
      : `Every ${interval} ${baseLabel.toLowerCase().replace(/y$/, 'ie')}s`.replace(
          'dailies',
          'days',
        );

  if (draft.recurrenceFrequency !== 2 || draft.recurrenceWeekdays.length === 0) {
    return prefix;
  }

  const dayLabels = RECURRENCE_WEEKDAY_OPTIONS
    .filter((item) => draft.recurrenceWeekdays.includes(item.value))
    .map((item) => item.label);

  if (dayLabels.length === 0) {
    return prefix;
  }

  return `${prefix} on ${dayLabels.join(', ')}`;
}

export function buildRecurrenceRule(
  draft: EventDraft,
): ScheduledEventCreateRequest['recurrence_rule'] {
  if (!draft.recurrenceEnabled || !draft.startDate || !draft.startTime) {
    return null;
  }

  const intervalRaw = Number(draft.recurrenceInterval);
  const interval = Number.isFinite(intervalRaw) && intervalRaw > 0 ? Math.floor(intervalRaw) : 1;
  const recurrenceRule: NonNullable<ScheduledEventCreateRequest['recurrence_rule']> = {
    start: combineDateAndTime(draft.startDate, draft.startTime),
    frequency: draft.recurrenceFrequency,
    interval,
  };

  if (draft.recurrenceFrequency === 2 && draft.recurrenceWeekdays.length > 0) {
    recurrenceRule.by_weekday = [...draft.recurrenceWeekdays].sort((a, b) => a - b);
  }

  return recurrenceRule;
}

export function getAnnouncementChannelOptions(channels: DiscordChannel[]) {
  return channels
    .filter((channel) => channel.type === 0 || channel.type === 5)
    .map((channel) => ({
      id: channel.id,
      name: channel.name,
      category: channel.category ?? undefined,
    }));
}

export function getEventChannelOptions(channels: DiscordChannel[]) {
  return channels
    .filter((channel) => channel.type === 2)
    .map((channel) => ({
      id: channel.id,
      name: channel.name,
      category: channel.category ?? undefined,
    }));
}

export function calculateScheduledEndTime(draft: EventDraft): string | null {
  if (draft.endMode === 'open') {
    return null;
  }

  if (draft.endMode === 'manual') {
    if (!draft.endDate || !draft.endTime) {
      return null;
    }
    return combineDateAndTime(draft.endDate, draft.endTime);
  }

  const durationMinutes = Number(draft.durationMinutes);
  if (!Number.isFinite(durationMinutes) || durationMinutes <= 0) {
    return null;
  }

  const start = new Date(combineDateAndTime(draft.startDate, draft.startTime));
  if (Number.isNaN(start.getTime())) {
    return null;
  }

  return new Date(start.getTime() + durationMinutes * 60000).toISOString();
}

export function validateDraft(draft: EventDraft): string | null {
  if (!draft.name.trim()) {
    return 'Event name is required.';
  }

  if (!draft.startDate || !draft.startTime) {
    return 'Start date and time are required.';
  }

  if (!draft.channelId) {
    return 'Voice events require a voice channel.';
  }

  if (!draft.announcementChannelId) {
    return 'Announcement channel is required.';
  }

  if (draft.endMode === 'manual' && ((!draft.endDate && draft.endTime) || (draft.endDate && !draft.endTime))) {
    return 'End date and time must be provided together.';
  }

  if (draft.endMode === 'duration') {
    const durationMinutes = Number(draft.durationMinutes);
    if (!Number.isFinite(durationMinutes) || durationMinutes <= 0) {
      return 'Duration must be greater than zero.';
    }
  }

  if (draft.recurrenceEnabled) {
    const intervalRaw = Number(draft.recurrenceInterval);
    if (!Number.isFinite(intervalRaw) || intervalRaw <= 0) {
      return 'Recurring interval must be greater than zero.';
    }

    if (draft.recurrenceFrequency === 2 && draft.recurrenceWeekdays.length === 0) {
      return 'Select at least one weekday for weekly recurrence.';
    }
  }

  const start = new Date(combineDateAndTime(draft.startDate, draft.startTime));
  if (Number.isNaN(start.getTime())) {
    return 'Start date or time is invalid.';
  }

  const end = calculateScheduledEndTime(draft);
  if (end) {
    const endDate = new Date(end);
    if (Number.isNaN(endDate.getTime()) || endDate.getTime() <= start.getTime()) {
      return 'End time must be after the start time.';
    }
  }

  return null;
}

export function getReviewHighlights(draft: EventDraft): string[] {
  const highlights: string[] = [];
  const signupRoleIds = draft.signupRoleIds ?? [];
  highlights.push('Voice attendance');

  if (draft.endMode === 'duration') {
    highlights.push(`Duration: ${formatDuration(draft.durationMinutes)}`);
  } else if (draft.endMode === 'open') {
    highlights.push('Open-ended');
  }

  if (signupRoleIds.length > 0) {
    highlights.push(`Signup roles: ${signupRoleIds.length}`);
  }

  if (draft.recurrenceEnabled) {
    highlights.push(formatRecurrenceSummary(draft));
  }

  return highlights;
}
