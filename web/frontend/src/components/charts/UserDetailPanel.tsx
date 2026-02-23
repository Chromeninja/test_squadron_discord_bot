/**
 * UserDetailPanel — Expandable panel showing per-user metrics breakdown.
 *
 * Displayed when clicking a user in a leaderboard chart.
 */

import { useEffect, useState } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { metricsApi, UserMetrics } from '../../api/endpoints';
import { handleApiError } from '../../utils/toast';

interface UserDetailPanelProps {
  userId: string;
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

export default function UserDetailPanel({ userId, days, onClose }: UserDetailPanelProps) {
  const [data, setData] = useState<UserMetrics | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    metricsApi
      .getUserMetrics(userId, days)
      .then((resp) => setData(resp.data))
      .catch((err) => handleApiError(err, 'Failed to load user metrics'))
      .finally(() => setLoading(false));
  }, [userId, days]);

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

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="bg-slate-800 border border-slate-700 rounded-xl max-w-2xl w-full max-h-[85vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700">
          <h3 className="text-lg font-semibold text-white">
            User Metrics — {userId.slice(-8)}…
          </h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition text-xl leading-none"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="p-6">
          {loading ? (
            <div className="flex items-center justify-center h-48 text-gray-400">
              Loading...
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

              {/* Activity chart */}
              {dailyData.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-gray-400 mb-3">Activity Trend</h4>
                  <ResponsiveContainer width="100%" height={180}>
                    <AreaChart data={dailyData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                      <defs>
                        <linearGradient id="userMsgGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
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
                        tick={{ fill: '#9ca3af', fontSize: 10 }}
                        axisLine={{ stroke: '#475569' }}
                        tickLine={false}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#1e293b',
                          border: '1px solid #334155',
                          borderRadius: '6px',
                          color: '#e2e8f0',
                          fontSize: '12px',
                        }}
                      />
                      <Area
                        type="monotone"
                        dataKey="messages"
                        stroke="#6366f1"
                        strokeWidth={2}
                        fill="url(#userMsgGrad)"
                        name="Messages"
                      />
                      <Area
                        type="monotone"
                        dataKey="voice_hours"
                        stroke="#22c55e"
                        strokeWidth={2}
                        fill="none"
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
