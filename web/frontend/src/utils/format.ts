/**
 * Shared formatting utilities.
 *
 * Single source of truth for duration, timestamp, and date formatting
 * used across Metrics, Charts, and User detail views.
 */

/**
 * Convert seconds to a compact human-readable duration.
 *
 * @example
 * formatDuration(45)    // "45s"
 * formatDuration(300)   // "5m"
 * formatDuration(7200)  // "2.0h"
 * formatDuration(360000) // "100h"
 */
export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  const hours = seconds / 3600;
  return hours < 100 ? `${hours.toFixed(1)}h` : `${Math.round(hours)}h`;
}

/**
 * Convert seconds to hours with one decimal place.
 *
 * @example
 * formatHours(7200) // "2.0h"
 */
export function formatHours(seconds: number): string {
  return `${(seconds / 3600).toFixed(1)}h`;
}

/**
 * Convert a Unix epoch (seconds) to a short date label ("Jan 5").
 */
export function formatTimestamp(epoch: number): string {
  const d = new Date(epoch * 1000);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

/**
 * Safely format a date value (ISO string or epoch seconds) to a
 * locale date string, returning "–" for missing / invalid values.
 */
export function formatDateValue(value: string | number | null | undefined): string {
  if (!value) return '-';
  try {
    const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value);
    if (Number.isNaN(date.getTime())) return '-';
    return date.toLocaleDateString();
  } catch {
    return '-';
  }
}
