/**
 * Shared activity-tier color mappings.
 *
 * Single source of truth consumed by Metrics, UserDetailPanel, and
 * UserDetailsModal so tier badge colours stay consistent everywhere.
 */

import type { ActivityTier } from '../api/endpoints';

// ── Solid badge colours (used on active filter chips) ──────────────────────
export const TIER_COLORS: Record<ActivityTier, string> = {
  hardcore: 'bg-red-600 text-white',
  regular: 'bg-amber-500 text-white',
  casual: 'bg-sky-500 text-white',
  reserve: 'bg-slate-500 text-white',
  inactive: 'bg-gray-700 text-gray-300',
};

// ── Outline badge colours (used on inactive filter chips) ──────────────────
export const TIER_COLORS_OUTLINE: Record<ActivityTier, string> = {
  hardcore: 'border-red-600 text-red-400',
  regular: 'border-amber-500 text-amber-400',
  casual: 'border-sky-500 text-sky-400',
  reserve: 'border-slate-500 text-slate-300',
  inactive: 'border-gray-600 text-gray-400',
};

// ── Translucent badge colours (UserDetailPanel & UserDetailsModal) ─────────
export const TIER_BADGE_COLORS: Record<string, string> = {
  hardcore: 'bg-red-600/20 text-red-400 border-red-600/40',
  regular: 'bg-amber-500/20 text-amber-400 border-amber-500/40',
  casual: 'bg-sky-500/20 text-sky-400 border-sky-500/40',
  reserve: 'bg-slate-500/20 text-slate-300 border-slate-500/40',
  inactive: 'bg-gray-700/20 text-gray-500 border-gray-600/40',
};

// ── Plain text colours (tier labels inside cards) ──────────────────────────
export const TIER_TEXT_COLORS: Record<string, string> = {
  hardcore: 'text-red-400',
  regular: 'text-amber-400',
  casual: 'text-sky-400',
  reserve: 'text-slate-300',
  inactive: 'text-gray-500',
};

// ── Labels ──────────────────────────────────────────────────────────────────
export const TIER_LABELS: Record<ActivityTier, string> = {
  hardcore: 'Hardcore',
  regular: 'Regular',
  casual: 'Casual',
  reserve: 'Reserve',
  inactive: 'Inactive',
};

// ── Tier icon mapping ──────────────────────────────────────────────────────
export const TIER_ICONS: Record<string, string> = {
  combined: '🌐',
  voice: '🎤',
  chat: '💬',
  game: '🎮',
};
