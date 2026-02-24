/**
 * Shared tier cadence helpers — used by Metrics page and UserDetailPanel.
 *
 * Centralises the cadence window descriptions so wording and behaviour
 * stay in sync across all views that present activity-tier information.
 */

import type { ActivityTier } from '../api/endpoints';

/** Cadence metadata for each non-inactive tier. */
export const TIER_CADENCE: Record<
  Exclude<ActivityTier, 'inactive'>,
  { windowDays: number; label: string }
> = {
  hardcore: { windowDays: 1, label: 'every day' },
  regular: { windowDays: 3, label: 'every 3 days' },
  casual: { windowDays: 7, label: 'every week' },
  reserve: { windowDays: 30, label: 'every month' },
};

/**
 * Build a human-readable description of what a tier means for a given
 * time-range.
 *
 * @param tier  - The activity tier to describe.
 * @param days  - The lookback range in days (e.g. 7, 30, 90).
 * @returns A short sentence, or empty string when the tier's window
 *          exceeds the range.
 */
export function getTierHelpText(tier: string, days: number): string {
  if (tier === 'inactive') {
    return `No qualifying activity pattern in the past ${days} days.`;
  }
  const cadence = TIER_CADENCE[tier as Exclude<ActivityTier, 'inactive'>];
  if (!cadence) return '';
  const { windowDays, label } = cadence;
  if (windowDays > days) return '';
  const numWindows = Math.ceil(days / windowDays);
  if (numWindows === 1) {
    return `Active at least once in the past ${days} days.`;
  }
  return `Active ${label} across the full ${days}-day period.`;
}
