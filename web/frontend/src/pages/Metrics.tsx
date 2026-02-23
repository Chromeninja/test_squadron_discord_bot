/**
 * Metrics Dashboard Page
 *
 * Displays server-wide and per-user activity metrics:
 * - Summary KPI cards (messages, voice time, averages)
 * - Time-series trend charts (messages per day, voice hours per day)
 * - Leaderboards (top users by voice, messages)
 * - Top games by play time
 * - Per-user drill-down on click
 */

import { useEffect, useState } from 'react';
import {
  metricsApi,
  MetricsOverview,
  VoiceLeaderboardEntry,
  MessageLeaderboardEntry,
  GameStatsEntry,
  TimeSeriesPoint,
} from '../api/endpoints';
import { handleApiError } from '../utils/toast';
import {
  MetricCard,
  TimeSeriesChart,
  LeaderboardChart,
  GamePieChart,
  UserDetailPanel,
} from '../components/charts';

type TimeRange = 7 | 30 | 90;

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  const hours = seconds / 3600;
  return hours < 100 ? `${hours.toFixed(1)}h` : `${Math.round(hours)}h`;
}

function formatHours(seconds: number): string {
  return `${(seconds / 3600).toFixed(1)}h`;
}

export default function Metrics() {
  const [days, setDays] = useState<TimeRange>(7);
  const [overview, setOverview] = useState<MetricsOverview | null>(null);
  const [voiceLeaderboard, setVoiceLeaderboard] = useState<VoiceLeaderboardEntry[]>([]);
  const [messageLeaderboard, setMessageLeaderboard] = useState<MessageLeaderboardEntry[]>([]);
  const [topGames, setTopGames] = useState<GameStatsEntry[]>([]);
  const [messageTimeSeries, setMessageTimeSeries] = useState<TimeSeriesPoint[]>([]);
  const [voiceTimeSeries, setVoiceTimeSeries] = useState<TimeSeriesPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);

  const fetchData = async (range: TimeRange) => {
    setLoading(true);
    setError(null);

    try {
      // Fetch all metrics data in parallel
      const [overviewResp, voiceResp, msgResp, gamesResp, msgTsResp, voiceTsResp] =
        await Promise.all([
          metricsApi.getOverview(range),
          metricsApi.getVoiceLeaderboard(range, 10),
          metricsApi.getMessageLeaderboard(range, 10),
          metricsApi.getTopGames(range, 10),
          metricsApi.getTimeSeries('messages', range),
          metricsApi.getTimeSeries('voice', range),
        ]);

      setOverview(overviewResp.data);
      setVoiceLeaderboard(voiceResp.entries);
      setMessageLeaderboard(msgResp.entries);
      setTopGames(gamesResp.games);
      setMessageTimeSeries(msgTsResp.data);
      setVoiceTimeSeries(voiceTsResp.data);
    } catch (err) {
      setError('Failed to load metrics data');
      handleApiError(err, 'Failed to load metrics');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData(days);
  }, [days]);

  const handleTimeRangeChange = (range: TimeRange) => {
    setDays(range);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400">
        <div className="text-center">
          <div className="animate-pulse text-2xl mb-2">📊</div>
          <div>Loading metrics...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-900/30 border border-red-700 rounded-lg p-6 text-center">
        <p className="text-red-400 mb-3">{error}</p>
        <button
          onClick={() => fetchData(days)}
          className="px-4 py-2 bg-red-700 text-white rounded hover:bg-red-600 transition text-sm"
        >
          Retry
        </button>
      </div>
    );
  }

  const period = overview?.period;
  const live = overview?.live;

  return (
    <div className="space-y-6">
      {/* Header with time range selector */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">Server Metrics</h2>
          <p className="text-sm text-gray-400 mt-1">
            Activity tracking &amp; analytics
            {live?.active_voice_users ? (
              <span className="text-green-400 ml-2">
                ● {live.active_voice_users} in voice now
              </span>
            ) : null}
          </p>
        </div>
        <div className="flex items-center gap-1 bg-slate-800 border border-slate-700 rounded-lg p-1">
          {([7, 30, 90] as TimeRange[]).map((range) => (
            <button
              key={range}
              onClick={() => handleTimeRangeChange(range)}
              className={`px-3 py-1.5 text-sm font-medium rounded transition ${
                days === range
                  ? 'bg-indigo-600 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-slate-700'
              }`}
            >
              {range}d
            </button>
          ))}
        </div>
      </div>

      {/* Summary KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard
          label="Total Messages"
          value={(period?.total_messages ?? 0).toLocaleString()}
          subtitle={`${period?.unique_messagers ?? 0} unique senders`}
          icon="💬"
        />
        <MetricCard
          label="Avg Messages / User"
          value={(period?.avg_messages_per_user ?? 0).toFixed(1)}
          subtitle={`Over ${days} days`}
          icon="📊"
        />
        <MetricCard
          label="Total Voice Time"
          value={formatDuration(period?.total_voice_seconds ?? 0)}
          subtitle={`${period?.unique_voice_users ?? 0} unique users`}
          icon="🎤"
        />
        <MetricCard
          label="Avg Voice / User"
          value={formatDuration(period?.avg_voice_per_user ?? 0)}
          subtitle={`Over ${days} days`}
          icon="⏱️"
        />
      </div>

      {/* Live activity row */}
      {live && (live.messages_today > 0 || live.active_game_sessions > 0 || live.top_game) && (
        <div className="bg-slate-800/50 border border-slate-700 rounded-lg px-5 py-3 flex items-center gap-6 text-sm">
          <span className="text-gray-400">Live:</span>
          <span className="text-gray-300">
            <span className="text-white font-medium">{live.messages_today}</span> messages today
          </span>
          {live.active_game_sessions > 0 && (
            <span className="text-gray-300">
              <span className="text-white font-medium">{live.active_game_sessions}</span> playing
            </span>
          )}
          {live.top_game && (
            <span className="text-gray-300">
              Top game: <span className="text-indigo-400">{live.top_game}</span>
            </span>
          )}
        </div>
      )}

      {/* Trend Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <TimeSeriesChart
          data={messageTimeSeries}
          title={`Messages per Day (${days}d)`}
          color="#6366f1"
          valueLabel="Messages"
        />
        <TimeSeriesChart
          data={voiceTimeSeries}
          title={`Voice Hours per Day (${days}d)`}
          color="#22c55e"
          valueLabel="Hours"
          formatValue={formatHours}
        />
      </div>

      {/* Leaderboards + Games */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <LeaderboardChart
          data={voiceLeaderboard.map((e) => ({
            user_id: e.user_id,
            value: e.total_seconds,
            username: e.username,
          }))}
          title="🎤 Voice Time Leaderboard"
          color="#22c55e"
          valueLabel="Time"
          formatValue={formatDuration}
          onBarClick={(userId) => setSelectedUserId(userId)}
        />
        <LeaderboardChart
          data={messageLeaderboard.map((e) => ({
            user_id: e.user_id,
            value: e.total_messages,
            username: e.username,
          }))}
          title="💬 Messages Leaderboard"
          color="#6366f1"
          valueLabel="Messages"
          onBarClick={(userId) => setSelectedUserId(userId)}
        />
        <GamePieChart data={topGames} title="🎮 Top Games" />
      </div>

      {/* Top Games Table (more detailed) */}
      {topGames.length > 0 && (
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
          <h3 className="text-sm font-semibold text-gray-300 mb-4">
            🎮 Game Statistics ({days}d)
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b border-slate-700">
                  <th className="pb-2 pr-4">#</th>
                  <th className="pb-2 pr-4">Game</th>
                  <th className="pb-2 pr-4 text-right">Total Time</th>
                  <th className="pb-2 pr-4 text-right">Sessions</th>
                  <th className="pb-2 pr-4 text-right">Avg Session</th>
                  <th className="pb-2 text-right">Players</th>
                </tr>
              </thead>
              <tbody>
                {topGames.map((game, i) => (
                  <tr
                    key={game.game_name}
                    className="border-b border-slate-700/50 text-gray-300"
                  >
                    <td className="py-2 pr-4 text-gray-500">{i + 1}</td>
                    <td className="py-2 pr-4 font-medium text-white">{game.game_name}</td>
                    <td className="py-2 pr-4 text-right text-indigo-400">
                      {formatDuration(game.total_seconds)}
                    </td>
                    <td className="py-2 pr-4 text-right">{game.session_count}</td>
                    <td className="py-2 pr-4 text-right">{formatDuration(game.avg_seconds)}</td>
                    <td className="py-2 text-right">{game.unique_players ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* User Detail Panel (modal) */}
      {selectedUserId && (
        <UserDetailPanel
          userId={selectedUserId}
          days={days}
          onClose={() => setSelectedUserId(null)}
        />
      )}
    </div>
  );
}
