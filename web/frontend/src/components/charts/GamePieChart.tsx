/**
 * GamePieChart — Pie/donut chart for top games by play time.
 *
 * Shows game distribution with hover details and a legend.
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

const COLORS = [
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

export default function GamePieChart({ data, title }: GamePieChartProps) {
  const chartData = data.map((game) => ({
    name: game.game_name,
    value: game.total_seconds,
    sessions: game.session_count,
    avgTime: game.avg_seconds,
    players: game.unique_players ?? 0,
  }));

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
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
            <Tooltip
              contentStyle={{
                backgroundColor: '#1e293b',
                border: '1px solid #334155',
                borderRadius: '6px',
                color: '#e2e8f0',
                fontSize: '12px',
              }}
              labelStyle={{ color: '#e2e8f0' }}
              itemStyle={{ color: '#e2e8f0' }}
              formatter={((value: number | undefined, _name: string | undefined, props: any) => {
                const { payload } = props;
                const v = value ?? 0;
                return [
                  <div key="tip" className="space-y-1 text-slate-200">
                    <div>Total: {formatDuration(v)}</div>
                    <div>Sessions: {payload.sessions}</div>
                    <div>Avg: {formatDuration(payload.avgTime)}</div>
                    {payload.players > 0 && <div>Players: {payload.players}</div>}
                  </div>,
                  '',
                ];
              }) as any}
            />
            <Legend
              wrapperStyle={{ fontSize: '11px', color: '#9ca3af' }}
              formatter={(value) => (
                <span className="text-gray-400 text-xs">{value}</span>
              )}
            />
          </PieChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
