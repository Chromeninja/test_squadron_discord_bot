/**
 * UserMetricsPanel — Shared metrics display for a single user.
 *
 * Shows activity-tier badges, summary statistics, an activity trend chart,
 * and top-games list.  Designed to be embedded inside any container:
 *   - UserDetailsModal (Users/Voice pages)
 *   - UserDetailPanel  (Metrics page leaderboard drill-down)
 *
 * AI Notes:
 *   This component is purely presentational — all data fetching is handled
 *   by the parent (or the useUserMetrics hook).  The activity chart reuses
 *   the same Recharts pattern from UserDetailPanel but is isolated here so
 *   both modal contexts get the chart for free.
 */

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { UserMetrics } from '../../api/endpoints';
import { Spinner } from '../ui';
import { getTierHelpText } from '../../utils/tierHelpers';
import { formatDuration, formatTimestamp } from '../../utils/format';
import { TIER_BADGE_COLORS, TIER_ICONS } from '../../utils/tierColors';
import { CHART_TOOLTIP_STYLE } from '../../utils/chartStyles';

// ── Tier badge (reused from UserDetailPanel) ────────────────────────────────

function TierBadge({
  label,
  tier,
  days = 30,
}: {
  label: string;
  tier: string | null | undefined;
  days?: number;
}) {
  const t = tier ?? 'inactive';
  const colorClass = TIER_BADGE_COLORS[t] || TIER_BADGE_COLORS.inactive;
  return (
    <div
      title={getTierHelpText(t, days)}
      className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md border text-xs font-medium ${colorClass}`}
    >
      <span>{TIER_ICONS[label] ?? ''}</span>
      <span className="text-gray-400">{label.charAt(0).toUpperCase() + label.slice(1)}</span>
      <span className="capitalize">{t}</span>
    </div>
  );
}

// ── Daily aggregation helper ────────────────────────────────────────────────

function aggregateDaily(
  timeseries: UserMetrics['timeseries'],
): Array<{
  day: string;
  messages: number;
  voice_hours: number;
  game_hours: number;
}> {
  if (!timeseries || timeseries.length === 0) return [];
  const map = new Map<
    string,
    { day: string; messages: number; voice_hours: number; game_hours: number }
  >();

  // Aggregate messages and voice
  for (const pt of timeseries) {
    const dayKey = formatTimestamp(pt.timestamp);
    const existing = map.get(dayKey);
    if (existing) {
      existing.messages += pt.messages;
      existing.voice_hours += pt.voice_seconds / 3600;
    } else {
      map.set(dayKey, {
        day: dayKey,
        messages: pt.messages,
        voice_hours: pt.voice_seconds / 3600,
        game_hours: 0,
      });
    }
  }

  // Note: Currently, game_hours is initialized to 0 since the API provides
  // only aggregated game totals, not hourly breakdowns. A future enhancement
  // would request hourly game session data from the backend API.

  return Array.from(map.values());
}

// ── Main component ──────────────────────────────────────────────────────────

export interface UserMetricsPanelProps {
  /** Fetched metrics data (null when unavailable). */
  metrics: UserMetrics | null;
  /** True while the API call is in flight. */
  loading: boolean;
  /** Non-null error message when the fetch failed. */
  error: string | null;
  /** Lookback window in days — used for tier tooltip text. */
  days?: number;
  /** When true, show the activity trend chart. Defaults to true. */
  showChart?: boolean;
}

export function UserMetricsPanel({
  metrics,
  loading,
  error,
  days = 30,
  showChart = true,
}: UserMetricsPanelProps) {
  // ── Loading state ───────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex items-center justify-center py-6 text-gray-500 text-sm">
        <Spinner className="mr-2 text-gray-400" label="Loading metrics…" />
      </div>
    );
  }

  // ── Error state ─────────────────────────────────────────────────────────
  if (error) {
    return (
      <div className="rounded-lg border border-amber-700/50 bg-amber-900/20 p-3 text-sm text-amber-300">
        {error}
      </div>
    );
  }

  // ── No data ─────────────────────────────────────────────────────────────
  if (!metrics) {
    return null;
  }

  const hasTiers =
    metrics.combined_tier || metrics.voice_tier || metrics.chat_tier || metrics.game_tier;

  const dailyData = showChart ? aggregateDaily(metrics.timeseries) : [];

  return (
    <div className="space-y-4">
      {/* ── Activity Tier Badges ──────────────────────────────────────────── */}
      {hasTiers && (
        <div className="bg-slate-900/50 rounded-lg p-4">
          <div className="text-xs text-gray-500 uppercase tracking-wider mb-3">
            Activity Levels{' '}
            <span className="normal-case text-gray-600">(last {days} days)</span>
          </div>
          <div className="flex flex-wrap gap-2">
            <TierBadge label="combined" tier={metrics.combined_tier} days={days} />
            <TierBadge label="voice" tier={metrics.voice_tier} days={days} />
            <TierBadge label="chat" tier={metrics.chat_tier} days={days} />
            <TierBadge label="game" tier={metrics.game_tier} days={days} />
          </div>
        </div>
      )}

      {/* ── Summary Statistics ────────────────────────────────────────────── */}
      <div className="bg-slate-900/50 rounded-lg p-4">
        <div className="text-xs text-gray-500 uppercase tracking-wider mb-3">
          Metrics Summary
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div className="bg-slate-900 rounded-lg p-3">
            <div className="text-xs text-gray-500">Total Messages</div>
            <div className="text-xl font-bold text-white">
              {metrics.total_messages.toLocaleString()}
            </div>
            <div className="text-[10px] text-gray-500">
              {metrics.avg_messages_per_day.toFixed(1)}/day
            </div>
          </div>
          <div className="bg-slate-900 rounded-lg p-3">
            <div className="text-xs text-gray-500">Voice Time</div>
            <div className="text-xl font-bold text-white">
              {formatDuration(metrics.total_voice_seconds)}
            </div>
            <div className="text-[10px] text-gray-500">
              {formatDuration(metrics.avg_voice_per_day)}/day
            </div>
          </div>
          <div className="col-span-2 bg-slate-900 rounded-lg p-3">
            <div className="text-xs text-gray-500 uppercase">Top Games</div>
            {metrics.top_games.length > 0 ? (
              <div className="mt-1 space-y-1">
                {metrics.top_games.slice(0, 3).map((game, i) => (
                  <div key={game.game_name} className="flex items-center justify-between">
                    <span className="text-gray-300 truncate mr-2">
                      <span className="text-gray-500 text-[10px] mr-1">#{i + 1}</span>
                      {game.game_name}
                    </span>
                    <span className="text-indigo-400 text-xs font-medium whitespace-nowrap">
                      {formatDuration(game.total_seconds)}
                    </span>
                  </div>
                ))}
                {metrics.top_games.length > 3 && (
                  <div className="text-[10px] text-gray-600">
                    +{metrics.top_games.length - 3} more
                  </div>
                )}
              </div>
            ) : (
              <div className="text-gray-600 mt-1">No game activity</div>
            )}
          </div>
        </div>
      </div>

      {/* ── Activity Trend Chart ──────────────────────────────────────────── */}
      {showChart && dailyData.length > 0 && (
        <div className="bg-slate-900/50 rounded-lg p-4">
          <div className="text-xs text-gray-500 uppercase tracking-wider mb-3">
            Activity Trend
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={dailyData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
              <defs>
                <linearGradient id="panelMsgGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="panelVoiceGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#22c55e" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="panelGameGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#f97316" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#f97316" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis
                dataKey="day"
                tick={{ fill: '#9ca3af', fontSize: 10 }}
                axisLine={{ stroke: '#475569' }}
                tickLine={false}
              />
              <YAxis
                yAxisId="left"
                tick={{ fill: '#818cf8', fontSize: 10 }}
                axisLine={{ stroke: '#475569' }}
                tickLine={false}
              />
              <YAxis
                yAxisId="right"
                orientation="right"
                tick={{ fill: '#4ade80', fontSize: 10 }}
                axisLine={{ stroke: '#475569' }}
                tickLine={false}
                tickFormatter={(v: number) => `${v.toFixed(1)}h`}
              />
              <Tooltip
                contentStyle={CHART_TOOLTIP_STYLE}
                formatter={
                  ((value: number | undefined, name: string | undefined) => {
                    if (name === 'Voice (hrs)' || name === 'Gaming (hrs)')
                      return [`${(value ?? 0).toFixed(1)}h`, name];
                    return [(value ?? 0).toLocaleString(), name ?? ''];
                  }) as any
                }
              />
              <Legend wrapperStyle={{ fontSize: '11px', color: '#9ca3af' }} />
              <Area
                yAxisId="left"
                type="monotone"
                dataKey="messages"
                stroke="#6366f1"
                strokeWidth={2}
                fill="url(#panelMsgGrad)"
                name="Messages"
              />
              <Area
                yAxisId="right"
                type="monotone"
                dataKey="voice_hours"
                stroke="#22c55e"
                strokeWidth={2}
                fill="url(#panelVoiceGrad)"
                name="Voice (hrs)"
              />
              <Area
                yAxisId="right"
                type="monotone"
                dataKey="game_hours"
                stroke="#f97316"
                strokeWidth={2}
                fill="url(#panelGameGrad)"
                name="Gaming (hrs)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* ── Full Top Games List (when chart is shown) ─────────────────────── */}
      {showChart && metrics.top_games.length > 3 && (
        <div className="bg-slate-900/50 rounded-lg p-4">
          <div className="text-xs text-gray-500 uppercase tracking-wider mb-3">
            All Games
          </div>
          <div className="space-y-2">
            {metrics.top_games.map((game, i) => (
              <div
                key={game.game_name}
                className="flex items-center justify-between bg-slate-900 rounded-lg px-4 py-2"
              >
                <div className="flex items-center gap-3">
                  <span className="text-xs text-gray-500 w-5">#{i + 1}</span>
                  <span className="text-sm text-gray-200">{game.game_name}</span>
                </div>
                <span className="text-sm font-medium text-indigo-400">
                  {formatDuration(game.total_seconds)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
