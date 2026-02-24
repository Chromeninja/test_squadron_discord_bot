/**
 * Shared membership-status helpers.
 *
 * Single source of truth for mapping membership statuses to badge variants
 * and display labels.  Consumed by Users table, UserDetailsModal, Badge, and
 * BulkRecheckResultsModal.
 */

import type { BadgeVariant } from './theme';

/**
 * Map a membership status string to a Badge variant.
 */
export function getStatusVariant(
  status: string | null,
): 'success' | 'info' | 'warning' | 'neutral' {
  switch (status) {
    case 'main':
      return 'success';
    case 'affiliate':
      return 'info';
    case 'non_member':
      return 'warning';
    default:
      return 'neutral';
  }
}

/**
 * Map a membership status string to a Badge variant (typed as BadgeVariant).
 */
export const STATUS_VARIANT_MAP: Record<string, BadgeVariant> = {
  main: 'success',
  affiliate: 'info',
  non_member: 'neutral',
};

/**
 * Canonical display labels for every membership status.
 *
 * Prefer importing from `theme.ts` (`membershipStatusLabels`) for the
 * full set; this re-export keeps backward-compat for call-sites that
 * referenced a local `getStatusLabel`.
 */
export const STATUS_LABELS: Record<string, string> = {
  main: 'Main',
  affiliate: 'Affiliate',
  non_member: 'Not Member',
  unknown: 'Unknown',
  unverified: 'Unverified',
  not_verified: 'Not Verified',
};

/** Get a human-friendly label for a membership status. */
export function getStatusLabel(status: string): string {
  return STATUS_LABELS[status] || status;
}
