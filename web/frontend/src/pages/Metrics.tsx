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

import { useEffect, useRef, useState } from 'react';
import {
  metricsApi,
  MetricsOverview,
  VoiceLeaderboardEntry,
  MessageLeaderboardEntry,
  GameStatsEntry,
  TimeSeriesPoint,
  ActivityDimension,
  ActivityTier,
  ActivityGroupCounts,
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

const TIER_LABELS: Record<ActivityTier, string> = {
  hardcore: 'Hardcore',
  regular: 'Regular',
  casual: 'Casual',
  reserve: 'Reserve',
  inactive: 'Inactive',
};

const TIER_COLORS: Record<ActivityTier, string> = {
  hardcore: 'bg-red-600 text-white',
  regular: 'bg-amber-500 text-white',
  casual: 'bg-sky-500 text-white',
  reserve: 'bg-slate-500 text-white',
  inactive: 'bg-gray-700 text-gray-300',
};

const TIER_COLORS_OUTLINE: Record<ActivityTier, string> = {
  hardcore: 'border-red-600 text-red-400',
  regular: 'border-amber-500 text-amber-400',
  casual: 'border-sky-500 text-sky-400',
  reserve: 'border-slate-500 text-slate-300',
  inactive: 'border-gray-600 text-gray-400',
};

const DIMENSIONS: { value: ActivityDimension; label: string }[] = [
  { value: 'all', label: '🌐 All Activity' },
  { value: 'voice', label: '🎤 Voice' },
  { value: 'chat', label: '💬 Chat' },
  { value: 'game', label: '🎮 Game-in-Voice' },
];

const ALL_TIERS: ActivityTier[] = ['hardcore', 'regular', 'casual', 'reserve', 'inactive'];

const TIER_HELP_TEXT: Record<ActivityTier, string> = {
  hardcore: 'Active within the last 24 hours (daily active).',
  regular: 'Active within the last 3 days.',
  casual: 'Active within the last 7 days (weekly active).',
  reserve: 'Active within the last 30 days (monthly active).',
  inactive: 'No qualifying activity in the last 30 days.',
};

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
  const [selectedUsername, setSelectedUsername] = useState<string | null>(null);
  const [selectedDimensions, setSelectedDimensions] = useState<ActivityDimension[]>(['all']);
  const [selectedTiers, setSelectedTiers] = useState<ActivityTier[]>([]);
  const [dimensionDropdownOpen, setDimensionDropdownOpen] = useState<boolean>(false);
  const [activityCounts, setActivityCounts] = useState<ActivityGroupCounts | null>(null);
  const dimensionDropdownRef = useRef<HTMLDivElement | null>(null);

  const fetchData = async (range: TimeRange, dims?: ActivityDimension[], tiers?: ActivityTier[]) => {
    setLoading(true);
    setError(null);

    const filterDims = dims ?? selectedDimensions;
    const filterTiers = tiers ?? selectedTiers;
    const hasSpecificDim = filterDims.some((value) => value !== 'all');
    const specificDims: ActivityDimension[] = filterDims.filter(
      (value): value is Exclude<ActivityDimension, 'all'> => value !== 'all'
    );
    const filterParam: ActivityDimension[] | undefined = hasSpecificDim
      ? specificDims
      : (filterTiers.length > 0 ? ['all'] : undefined);
    const tierParam: ActivityTier[] | undefined = filterTiers.length > 0 ? filterTiers : undefined;

    try {
      // Fetch all metrics data in parallel (include activity group counts)
      const [overviewResp, voiceResp, msgResp, gamesResp, msgTsResp, voiceTsResp, groupsResp] =
        await Promise.all([
          metricsApi.getOverview(range, filterParam, tierParam),
          metricsApi.getVoiceLeaderboard(range, 10, filterParam, tierParam),
          metricsApi.getMessageLeaderboard(range, 10, filterParam, tierParam),
          metricsApi.getTopGames(range, 10, filterParam, tierParam),
          metricsApi.getTimeSeries('messages', range, filterParam, tierParam),
          metricsApi.getTimeSeries('voice', range, filterParam, tierParam),
          metricsApi.getActivityGroups(range, filterParam, tierParam),
        ]);

      setOverview(overviewResp.data);
      setVoiceLeaderboard(voiceResp.entries);
      setMessageLeaderboard(msgResp.entries);
      setTopGames(gamesResp.games);
      setMessageTimeSeries(msgTsResp.data);
      setVoiceTimeSeries(voiceTsResp.data);
      setActivityCounts(groupsResp.data);
    } catch (err) {
      setError('Failed to load metrics data');
      handleApiError(err, 'Failed to load metrics');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData(days);
  }, [days, selectedDimensions, selectedTiers]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (!dimensionDropdownRef.current) return;
      if (!dimensionDropdownRef.current.contains(event.target as Node)) {
        setDimensionDropdownOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleTimeRangeChange = (range: TimeRange) => {
    setDays(range);
  };

  const handleTierClick = (tier: ActivityTier) => {
    setSelectedTiers((prev) => (prev.includes(tier) ? prev.filter((t) => t !== tier) : [...prev, tier]));
  };

  const toggleDimension = (dimension: ActivityDimension) => {
    if (dimension === 'all') {
      setSelectedDimensions(['all']);
      return;
    }
    setSelectedDimensions((prev) => {
      const withoutAll = prev.filter((value) => value !== 'all');
      if (withoutAll.includes(dimension)) {
        const next = withoutAll.filter((value) => value !== dimension);
        return next.length > 0 ? next : ['all'];
      }
      return [...withoutAll, dimension];
    });
  };

  const openUserPanel = (userId: string) => {
    const voiceEntry = voiceLeaderboard.find((entry) => entry.user_id === userId);
    const messageEntry = messageLeaderboard.find((entry) => entry.user_id === userId);
    setSelectedUsername(voiceEntry?.username ?? messageEntry?.username ?? null);
    setSelectedUserId(userId);
  };

  // Get the tier counts for the currently selected dimension
  const currentDimensionForCounts: ActivityDimension = selectedDimensions.length === 1 ? selectedDimensions[0] : 'all';
  const currentCounts = activityCounts?.[currentDimensionForCounts] ?? null;

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

      {/* Activity Group Filter */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Dimension dropdown (Users-page style) */}
        <div className="flex-1 min-w-[250px] max-w-[420px] relative" ref={dimensionDropdownRef}>
          <div className="relative">
            <div
              className="w-full bg-slate-900 border border-slate-600 rounded px-4 py-2 text-white cursor-pointer hover:border-slate-500 transition-colors min-h-[42px] flex items-center justify-between"
              onClick={() => setDimensionDropdownOpen((prev) => !prev)}
            >
              <div className="flex flex-wrap gap-1 flex-1 min-h-[26px]">
                {selectedDimensions.length === 1 && selectedDimensions[0] === 'all' ? (
                  <span className="text-gray-500">All Activity Groups</span>
                ) : (
                  selectedDimensions.map((dimension) => {
                    const dim = DIMENSIONS.find((item) => item.value === dimension);
                    return (
                      <button
                        key={dimension}
                        type="button"
                        className="px-2 py-0.5 text-xs rounded bg-indigo-900/30 text-indigo-300 border border-indigo-700/50 flex items-center gap-1 hover:bg-indigo-900/50"
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleDimension(dimension);
                        }}
                        aria-label={`Remove ${dim?.label || dimension} filter`}
                      >
                        {dim?.label || dimension}
                        <span aria-hidden="true">×</span>
                      </button>
                    );
                  })
                )}
              </div>
              <span className="text-gray-400 ml-2">{dimensionDropdownOpen ? '▲' : '▼'}</span>
            </div>

            {dimensionDropdownOpen && (
              <div className="absolute z-10 w-full mt-1 bg-slate-900 border border-slate-600 rounded shadow-lg max-h-64 overflow-hidden">
                <div className="max-h-48 overflow-y-auto">
                  {DIMENSIONS.map((dimension) => (
                    <label
                      key={dimension.value}
                      className="flex items-center px-4 py-2 hover:bg-slate-800 cursor-pointer text-white text-sm"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <input
                        type="checkbox"
                        checked={selectedDimensions.includes(dimension.value)}
                        onChange={() => toggleDimension(dimension.value)}
                        className="mr-3 h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-slate-600 rounded"
                      />
                      {dimension.label}
                    </label>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Tier chips */}
        <div className="flex items-center gap-1.5">
          {ALL_TIERS.map((tier) => {
            const count = currentCounts?.[tier] ?? 0;
            const isActive = selectedTiers.includes(tier);
            return (
              <div key={tier} className="relative group">
                <button
                  onClick={() => handleTierClick(tier)}
                  title={TIER_HELP_TEXT[tier]}
                  className={`inline-flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-full border transition ${
                    isActive
                      ? TIER_COLORS[tier]
                      : TIER_COLORS_OUTLINE[tier] + ' bg-transparent hover:bg-slate-800'
                  }`}
                >
                  {TIER_LABELS[tier]}
                  <span
                    className={`inline-flex items-center justify-center text-[10px] min-w-[18px] h-[18px] rounded-full px-1 ${
                      isActive ? 'bg-black/25' : 'bg-slate-800'
                    }`}
                  >
                    {count}
                  </span>
                </button>
                <div className="pointer-events-none absolute left-1/2 -translate-x-1/2 -top-10 hidden group-hover:block z-20">
                  <div className="whitespace-nowrap rounded bg-slate-900 border border-slate-600 px-2 py-1 text-[11px] text-gray-200 shadow-lg">
                    {TIER_HELP_TEXT[tier]}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Active filter indicator */}
        {(selectedTiers.length > 0 || !(selectedDimensions.length === 1 && selectedDimensions[0] === 'all')) && (
          <button
            onClick={() => {
              setSelectedTiers([]);
              setSelectedDimensions(['all']);
            }}
            className="text-xs text-gray-400 hover:text-white transition"
          >
            ✕ Clear filters
          </button>
        )}
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
          onBarClick={openUserPanel}
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
          onBarClick={openUserPanel}
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
          username={selectedUsername}
          days={days}
          onClose={() => {
            setSelectedUserId(null);
            setSelectedUsername(null);
          }}
        />
      )}
    </div>
  );
}
