/**
 * GameDetailPanel — Modal showing detailed metrics for a selected game.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { GameMetricsDetail, metricsApi } from '../../api/endpoints';
import { CHART_TOOLTIP_STYLE } from '../../utils/chartStyles';
import { formatDuration, formatTimestamp } from '../../utils/format';
import { handleApiError } from '../../utils/toast';

interface GameDetailPanelProps {
  gameName: string;
  days: number;
  onClose: () => void;
}

export default function GameDetailPanel({ gameName, days, onClose }: GameDetailPanelProps) {
  const [data, setData] = useState<GameMetricsDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchGameMetrics = useCallback(() => {
    setLoading(true);
    setError(null);
    metricsApi
      .getGameMetrics(gameName, days, 5)
      .then((response) => setData(response.data))
      .catch((err) => {
        setError('Failed to load game metrics');
        handleApiError(err, 'Failed to load game metrics');
      })
      .finally(() => setLoading(false));
  }, [days, gameName]);

  useEffect(() => {
    fetchGameMetrics();
  }, [fetchGameMetrics]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const dailyTrend = useMemo(() => {
    if (!data?.timeseries?.length) return [];

    const byDay = new Map<string, { day: string; total_hours: number; unique_users: number }>();
    for (const point of data.timeseries) {
      const day = formatTimestamp(point.timestamp);
      const existing = byDay.get(day);
      const valueHours = (point.value ?? 0) / 3600;
      const uniqueUsers = point.unique_users ?? 0;
      if (existing) {
        existing.total_hours += valueHours;
        existing.unique_users = Math.max(existing.unique_users, uniqueUsers);
      } else {
        byDay.set(day, {
          day,
          total_hours: valueHours,
          unique_users: uniqueUsers,
        });
      }
    }

    return Array.from(byDay.values());
  }, [data?.timeseries]);

  return (
    <div
      className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      role="dialog"
      aria-modal="true"
      aria-label={`Game metrics for ${gameName}`}
    >
      <div className="bg-slate-800 border border-slate-700 rounded-xl max-w-2xl w-full max-h-[85vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700">
          <h3 className="text-lg font-semibold text-white truncate pr-3">
            🎮 Game Metrics — {data?.game_name || gameName}
          </h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition text-xl leading-none"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div className="p-6">
          {loading ? (
            <div className="flex items-center justify-center h-48 text-gray-400">
              <div className="text-center">
                <div className="animate-pulse text-2xl mb-2">🎮</div>
                <div>Loading...</div>
              </div>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center h-48 gap-3">
              <p className="text-red-400 text-sm">{error}</p>
              <button
                onClick={fetchGameMetrics}
                className="px-4 py-2 bg-red-700 text-white rounded hover:bg-red-600 transition text-sm"
              >
                Retry
              </button>
            </div>
          ) : !data ? (
            <div className="flex items-center justify-center h-48 text-gray-500">
              No metrics found for this game
            </div>
          ) : (
            <div className="space-y-6">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-slate-900 rounded-lg p-3">
                  <div className="text-xs text-gray-500">Total Time</div>
                  <div className="text-xl font-bold text-white">{formatDuration(data.total_seconds)}</div>
                </div>
                <div className="bg-slate-900 rounded-lg p-3">
                  <div className="text-xs text-gray-500">Sessions</div>
                  <div className="text-xl font-bold text-white">{data.session_count.toLocaleString()}</div>
                </div>
                <div className="bg-slate-900 rounded-lg p-3">
                  <div className="text-xs text-gray-500">Avg Session</div>
                  <div className="text-xl font-bold text-white">{formatDuration(data.avg_seconds)}</div>
                </div>
                <div className="bg-slate-900 rounded-lg p-3">
                  <div className="text-xs text-gray-500">Players</div>
                  <div className="text-xl font-bold text-white">{data.unique_players.toLocaleString()}</div>
                </div>
              </div>

              {dailyTrend.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-gray-400 mb-3">Playtime Trend</h4>
                  <ResponsiveContainer width="100%" height={200}>
                    <AreaChart data={dailyTrend} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                      <defs>
                        <linearGradient id="gamePlayGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.25} />
                          <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
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
                        tick={{ fill: '#fbbf24', fontSize: 10 }}
                        axisLine={{ stroke: '#475569' }}
                        tickLine={false}
                        tickFormatter={(value: number) => `${value.toFixed(1)}h`}
                      />
                      <YAxis
                        yAxisId="right"
                        orientation="right"
                        tick={{ fill: '#60a5fa', fontSize: 10 }}
                        axisLine={{ stroke: '#475569' }}
                        tickLine={false}
                      />
                      <Tooltip
                        contentStyle={CHART_TOOLTIP_STYLE}
                        formatter={((value: number | undefined, name: string | undefined) => {
                          if (name === 'Playtime') return [`${(value ?? 0).toFixed(1)}h`, name];
                          return [(value ?? 0).toLocaleString(), name ?? ''];
                        }) as any}
                      />
                      <Area
                        yAxisId="left"
                        type="monotone"
                        dataKey="total_hours"
                        stroke="#f59e0b"
                        strokeWidth={2}
                        fill="url(#gamePlayGrad)"
                        name="Playtime"
                      />
                      <Area
                        yAxisId="right"
                        type="monotone"
                        dataKey="unique_users"
                        stroke="#60a5fa"
                        strokeWidth={2}
                        fill="none"
                        name="Unique Players"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}

              <div>
                <h4 className="text-sm font-medium text-gray-400 mb-3">Top Players</h4>
                {data.top_players.length === 0 ? (
                  <div className="text-sm text-gray-500 bg-slate-900 rounded-lg px-4 py-3">
                    No players found for this period
                  </div>
                ) : (
                  <div className="space-y-2">
                    {data.top_players.map((player, index) => (
                      <div
                        key={`${player.user_id}-${index}`}
                        className="flex items-center justify-between bg-slate-900 rounded-lg px-4 py-2"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <span className="text-xs text-gray-500 w-5">#{index + 1}</span>
                          <span className="text-sm text-gray-200 truncate">
                            {(player.username?.trim() || `User ${player.user_id.slice(-6)}`)}
                          </span>
                        </div>
                        <div className="text-right">
                          <div className="text-sm font-medium text-amber-400">{formatDuration(player.total_seconds)}</div>
                          <div className="text-[11px] text-gray-500">{player.session_count} sessions</div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
