/**
 * GamePieChart — Pie/donut chart for top games by play time.
 *
 * Shows game distribution with hover details, percentages, and a legend.
 */

import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';

interface GameEntry {
  game_name: string;
  total_seconds: number;
  session_count: number;
  avg_seconds: number;
  unique_players?: number;
}

interface GamePieChartProps {
  data: GameEntry[];
  title: string;
}

/** Exported for use in game statistics table color dots. */
export const COLORS = [
  '#6366f1', // indigo
  '#8b5cf6', // violet
  '#a855f7', // purple
  '#ec4899', // pink
  '#f43f5e', // rose
  '#f97316', // orange
  '#eab308', // yellow
  '#22c55e', // green
  '#14b8a6', // teal
  '#06b6d4', // cyan
];

function formatDuration(seconds: number): string {
  if (seconds < 3600) {
    return `${Math.round(seconds / 60)}m`;
  }
  const hours = seconds / 3600;
  if (hours < 100) {
    return `${hours.toFixed(1)}h`;
  }
  return `${Math.round(hours)}h`;
}

/** Custom tooltip content for the pie chart — fixes game name display. */
function CustomPieTooltip({ active, payload }: any) {
  if (!active || !payload || payload.length === 0) return null;
  const entry = payload[0];
  const { name, value, sessions, avgTime, players } = entry.payload;
  const total = payload[0]?.payload?.total ?? value;
  const pct = total > 0 ? ((value / total) * 100).toFixed(1) : '0.0';
  return (
    <div
      className="space-y-1 text-slate-200"
      style={{
        backgroundColor: '#1e293b',
        border: '1px solid #334155',
        borderRadius: '6px',
        padding: '8px 12px',
        fontSize: '12px',
      }}
    >
      <div className="font-medium text-white">{name}</div>
      <div>Total: {formatDuration(value)} ({pct}%)</div>
      <div>Sessions: {sessions}</div>
      <div>Avg: {formatDuration(avgTime)}</div>
      {players > 0 && <div>Players: {players}</div>}
    </div>
  );
}

export default function GamePieChart({ data, title }: GamePieChartProps) {
  const totalSeconds = data.reduce((sum, g) => sum + g.total_seconds, 0);

  const chartData = data.map((game) => ({
    name: game.game_name,
    value: game.total_seconds,
    sessions: game.session_count,
    avgTime: game.avg_seconds,
    players: game.unique_players ?? 0,
    total: totalSeconds,
  }));

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-5" role="img" aria-label={`${title} pie chart`}>
      <h3 className="text-sm font-semibold text-gray-300 mb-4">{title}</h3>
      {chartData.length === 0 ? (
        <div className="flex items-center justify-center h-48 text-gray-500 text-sm">
          No game data available for this period
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={300}>
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="45%"
              innerRadius={55}
              outerRadius={90}
              paddingAngle={2}
              dataKey="value"
              nameKey="name"
            >
              {chartData.map((_, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={COLORS[index % COLORS.length]}
                  stroke="#1e293b"
                  strokeWidth={2}
                />
              ))}
            </Pie>
            <Tooltip content={<CustomPieTooltip />} />
            <Legend
              wrapperStyle={{ fontSize: '11px', color: '#9ca3af' }}
              formatter={(value: string, _entry: any, index: number) => {
                const pct = totalSeconds > 0
                  ? ((chartData[index]?.value ?? 0) / totalSeconds * 100).toFixed(0)
                  : '0';
                return (
                  <span className="text-gray-400 text-xs">{value} ({pct}%)</span>
                );
              }}
            />
          </PieChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
