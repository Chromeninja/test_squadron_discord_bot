/**
 * UserDetailPanel — Expandable panel showing per-user metrics breakdown.
 *
 * Displayed when clicking a user in a leaderboard chart.
 */

import { useCallback, useEffect, useState } from 'react';
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
import { metricsApi, UserMetrics } from '../../api/endpoints';
import { handleApiError } from '../../utils/toast';
import { getTierHelpText } from '../../utils/tierHelpers';

const TIER_BADGE_COLORS: Record<string, string> = {
  hardcore: 'bg-red-600/20 text-red-400 border-red-600/40',
  regular: 'bg-amber-500/20 text-amber-400 border-amber-500/40',
  casual: 'bg-sky-500/20 text-sky-400 border-sky-500/40',
  reserve: 'bg-slate-500/20 text-slate-300 border-slate-500/40',
  inactive: 'bg-gray-700/20 text-gray-500 border-gray-600/40',
};

const TIER_ICONS: Record<string, string> = {
  combined: '🌐',
  voice: '🎤',
  chat: '💬',
  game: '🎮',
};

// Tier cadence helpers imported from utils/tierHelpers

function TierBadge({ label, tier, days = 30 }: { label: string; tier: string | null | undefined; days?: number }) {
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

interface UserDetailPanelProps {
  userId: string;
  username?: string | null;
  days: number;
  onClose: () => void;
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  const hours = seconds / 3600;
  return hours < 100 ? `${hours.toFixed(1)}h` : `${Math.round(hours)}h`;
}

function formatTimestamp(epoch: number): string {
  const d = new Date(epoch * 1000);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

export default function UserDetailPanel({ userId, username, days, onClose }: UserDetailPanelProps) {
  const [data, setData] = useState<UserMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchUserMetrics = useCallback(() => {
    setLoading(true);
    setError(null);
    metricsApi
      .getUserMetrics(userId, days)
      .then((resp) => setData(resp.data))
      .catch((err) => {
        setError('Failed to load user metrics');
        handleApiError(err, 'Failed to load user metrics');
      })
      .finally(() => setLoading(false));
  }, [userId, days]);

  useEffect(() => {
    fetchUserMetrics();
  }, [fetchUserMetrics]);

  // Close modal on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  // Aggregate hourly timeseries to daily
  const dailyData = (() => {
    if (!data?.timeseries) return [];
    const map = new Map<string, { day: string; messages: number; voice_hours: number }>();
    for (const pt of data.timeseries) {
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
        });
      }
    }
    return Array.from(map.values());
  })();

  // Check if any tier badge should display
  const hasTiers = data && (data.combined_tier || data.voice_tier || data.chat_tier || data.game_tier);

  return (
    <div
      className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      role="dialog"
      aria-modal="true"
      aria-label={`User metrics for ${username || userId}`}
    >
      <div className="bg-slate-800 border border-slate-700 rounded-xl max-w-2xl w-full max-h-[85vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700">
          <div className="flex items-center gap-4 flex-wrap">
            <h3 className="text-lg font-semibold text-white">
              User Metrics — {(data?.username?.trim() || username?.trim()) ? (data?.username?.trim() || username?.trim()) : `${userId.slice(-8)}…`}
            </h3>
            {hasTiers && (
              <div className="flex items-center gap-1.5 flex-wrap">
                <TierBadge label="combined" tier={data.combined_tier} days={days} />
                <TierBadge label="voice" tier={data.voice_tier} days={days} />
                <TierBadge label="chat" tier={data.chat_tier} days={days} />
                <TierBadge label="game" tier={data.game_tier} days={days} />
              </div>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition text-xl leading-none"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="p-6">
          {loading ? (
            <div className="flex items-center justify-center h-48 text-gray-400">
              <div className="text-center">
                <div className="animate-pulse text-2xl mb-2">📊</div>
                <div>Loading...</div>
              </div>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center h-48 gap-3">
              <p className="text-red-400 text-sm">{error}</p>
              <button
                onClick={fetchUserMetrics}
                className="px-4 py-2 bg-red-700 text-white rounded hover:bg-red-600 transition text-sm"
              >
                Retry
              </button>
            </div>
          ) : !data ? (
            <div className="flex items-center justify-center h-48 text-gray-500">
              No metrics found for this user
            </div>
          ) : (
            <div className="space-y-6">
              {/* Summary stats */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-slate-900 rounded-lg p-3">
                  <div className="text-xs text-gray-500">Total Messages</div>
                  <div className="text-xl font-bold text-white">
                    {data.total_messages.toLocaleString()}
                  </div>
                </div>
                <div className="bg-slate-900 rounded-lg p-3">
                  <div className="text-xs text-gray-500">Avg Msgs/Day</div>
                  <div className="text-xl font-bold text-white">
                    {data.avg_messages_per_day.toFixed(1)}
                  </div>
                </div>
                <div className="bg-slate-900 rounded-lg p-3">
                  <div className="text-xs text-gray-500">Voice Time</div>
                  <div className="text-xl font-bold text-white">
                    {formatDuration(data.total_voice_seconds)}
                  </div>
                </div>
                <div className="bg-slate-900 rounded-lg p-3">
                  <div className="text-xs text-gray-500">Avg Voice/Day</div>
                  <div className="text-xl font-bold text-white">
                    {formatDuration(data.avg_voice_per_day)}
                  </div>
                </div>
              </div>

              {/* Activity chart — dual Y-axis for messages (left) and voice hours (right) */}
              {dailyData.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-gray-400 mb-3">Activity Trend</h4>
                  <ResponsiveContainer width="100%" height={200}>
                    <AreaChart data={dailyData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                      <defs>
                        <linearGradient id="userMsgGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                        </linearGradient>
                        <linearGradient id="userVoiceGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#22c55e" stopOpacity={0.15} />
                          <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
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
                        contentStyle={{
                          backgroundColor: '#1e293b',
                          border: '1px solid #334155',
                          borderRadius: '6px',
                          color: '#e2e8f0',
                          fontSize: '12px',
                        }}
                        formatter={((value: number | undefined, name: string | undefined) => {
                          if (name === 'Voice (hrs)') return [`${(value ?? 0).toFixed(1)}h`, name];
                          return [(value ?? 0).toLocaleString(), name ?? ''];
                        }) as any}
                      />
                      <Legend
                        wrapperStyle={{ fontSize: '11px', color: '#9ca3af' }}
                      />
                      <Area
                        yAxisId="left"
                        type="monotone"
                        dataKey="messages"
                        stroke="#6366f1"
                        strokeWidth={2}
                        fill="url(#userMsgGrad)"
                        name="Messages"
                      />
                      <Area
                        yAxisId="right"
                        type="monotone"
                        dataKey="voice_hours"
                        stroke="#22c55e"
                        strokeWidth={2}
                        fill="url(#userVoiceGrad)"
                        name="Voice (hrs)"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Top games */}
              {data.top_games.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-gray-400 mb-3">Top Games</h4>
                  <div className="space-y-2">
                    {data.top_games.map((game, i) => (
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
          )}
        </div>
      </div>
    </div>
  );
}
