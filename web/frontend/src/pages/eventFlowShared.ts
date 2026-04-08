import {
  type DiscordChannel,
  type EventModuleSettingsPayload,
  type ScheduledEventSummary,
} from '../api/endpoints';
import { type BadgeVariant } from '../utils/theme';

export type BuilderStep = 'details' | 'attendance' | 'connections' | 'review';
export type EndMode = 'duration' | 'manual' | 'open';
export type RecurrenceOption = 'once' | 'daily' | 'weekly' | 'biweekly' | 'monthly';
export type AttendanceMode = 'rsvp' | 'signup' | 'drop_in';
export type ReminderOffset = 'none' | '15m' | '1h' | '1d';

export interface EventDraft {
  name: string;
  description: string;
  entityType: 'voice' | 'external';
  channelId: string | null;
  location: string;
  startDate: string;
  startTime: string;
  endMode: EndMode;
  durationMinutes: string;
  endDate: string;
  endTime: string;
  recurrence: RecurrenceOption;
  attendanceMode: AttendanceMode;
  capacity: string;
  waitlistEnabled: boolean;
  reminderOffset: ReminderOffset;
  announcementChannelId: string | null;
  coordinatorNotes: string;
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
    id: 'attendance',
    title: 'Attendance',
    description: 'RSVP and signup behavior.',
  },
  {
    id: 'connections',
    title: 'Connections',
    description: 'Channels, reminders, and notes.',
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

export const RECURRENCE_OPTIONS: Array<{ value: RecurrenceOption; label: string }> = [
  { value: 'once', label: 'One-time event' },
  { value: 'daily', label: 'Daily cadence' },
  { value: 'weekly', label: 'Weekly cadence' },
  { value: 'biweekly', label: 'Every two weeks' },
  { value: 'monthly', label: 'Monthly cadence' },
];

export const REMINDER_OPTIONS: Array<{ value: ReminderOffset; label: string }> = [
  { value: 'none', label: 'No reminder' },
  { value: '15m', label: '15 minutes before' },
  { value: '1h', label: '1 hour before' },
  { value: '1d', label: '1 day before' },
];

export const ATTENDANCE_OPTIONS: Array<{
  id: AttendanceMode;
  title: string;
  description: string;
}> = [
  {
    id: 'rsvp',
    title: 'RSVP tracking',
    description: 'Best for fleet ops and events where you want a clean interested headcount.',
  },
  {
    id: 'signup',
    title: 'Structured signups',
    description: 'Use for trainings or limited-capacity activities where slots matter.',
  },
  {
    id: 'drop_in',
    title: 'Drop-in attendance',
    description: 'Useful for community hangs and low-friction, open-door sessions.',
  },
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
    entityType: 'voice',
    channelId: settings?.default_voice_channel_id ?? null,
    location: '',
    startDate: '',
    startTime: '',
    endMode: 'duration',
    durationMinutes: '120',
    endDate: '',
    endTime: '',
    recurrence: 'once',
    attendanceMode: 'rsvp',
    capacity: '',
    waitlistEnabled: false,
    reminderOffset: '1h',
    announcementChannelId: settings?.default_announcement_channel_id ?? null,
    coordinatorNotes: '',
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

  return {
    name: event.name,
    description: event.description ?? '',
    entityType: event.entity_type === 'external' ? 'external' : 'voice',
    channelId: event.channel_id ?? settings?.default_voice_channel_id ?? null,
    location: event.location ?? '',
    startDate: start.date,
    startTime: start.time,
    endMode: event.scheduled_end_time ? 'manual' : 'open',
    durationMinutes,
    endDate: end.date,
    endTime: end.time,
    recurrence: 'once',
    attendanceMode: 'rsvp',
    capacity: '',
    waitlistEnabled: false,
    reminderOffset: '1h',
    announcementChannelId: settings?.default_announcement_channel_id ?? null,
    coordinatorNotes: '',
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

  if (draft.entityType === 'external' && !draft.location.trim()) {
    return 'External events require a location.';
  }

  if (draft.entityType !== 'external' && !draft.channelId) {
    return 'Voice events require a voice channel.';
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
  highlights.push(draft.entityType === 'external' ? 'External destination' : 'Voice attendance');
  highlights.push(draft.recurrence === 'once' ? 'Single publish' : `${draft.recurrence} cadence`);
  highlights.push(
    draft.attendanceMode === 'signup'
      ? 'Structured signups'
      : draft.attendanceMode === 'drop_in'
        ? 'Drop-in attendance'
        : 'RSVP tracking',
  );

  if (draft.reminderOffset !== 'none') {
    highlights.push(`Reminder ${draft.reminderOffset} before`);
  }

  if (draft.capacity.trim()) {
    highlights.push(`Capacity ${draft.capacity.trim()}`);
  }

  return highlights;
}