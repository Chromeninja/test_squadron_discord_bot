/**
 * LeaderboardChart — Horizontal bar chart for top users (voice time / messages).
 *
 * Shows ranked list with bars, user IDs (or usernames if available), and values.
 */

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';

interface LeaderboardEntry {
  user_id: string | number;
  value: number;
  username?: string | null;
}

interface LeaderboardChartProps {
  data: LeaderboardEntry[];
  title: string;
  color?: string;
  /** Format function for values */
  formatValue?: (val: number) => string;
  /** Label for the value in tooltip */
  valueLabel?: string;
  /** Click handler when a bar is clicked */
  onBarClick?: (userId: string) => void;
}

/** Truncate long user names for Y-axis labels */
function truncateLabel(label: string, maxLen: number = 18): string {
  if (label.length <= maxLen) return label;
  return label.slice(0, maxLen - 1) + '…';
}

/** Custom tooltip showing full username + formatted value. */
function CustomLeaderboardTooltip({
  active,
  payload,
  fmtVal,
  valueLabel,
}: any) {
  if (!active || !payload || payload.length === 0) return null;
  const entry = payload[0]?.payload;
  if (!entry) return null;
  return (
    <div
      style={{
        backgroundColor: '#1e293b',
        border: '1px solid #334155',
        borderRadius: '6px',
        padding: '8px 12px',
        fontSize: '12px',
        color: '#e2e8f0',
      }}
    >
      <div className="font-medium text-white mb-1">#{entry.rank} {entry.name}</div>
      <div className="text-gray-300">
        {valueLabel}: {fmtVal(entry.value)}
      </div>
    </div>
  );
}

export default function LeaderboardChart({
  data,
  title,
  color = '#6366f1',
  formatValue,
  valueLabel = 'Value',
  onBarClick,
}: LeaderboardChartProps) {
  const chartData = data.map((entry, i) => ({
    name: entry.username || `User ${String(entry.user_id).slice(-6)}`,
    value: entry.value,
    userId: String(entry.user_id),
    rank: i + 1,
  }));

  const fmtVal = formatValue ?? ((v: number) => v.toLocaleString());

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-5" role="img" aria-label={`${title} bar chart`}>
      <h3 className="text-sm font-semibold text-gray-300 mb-4">{title}</h3>
      {chartData.length === 0 ? (
        <div className="flex items-center justify-center h-48 text-gray-500 text-sm">
          No data available for this period
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={Math.max(200, chartData.length * 36)}>
          <BarChart
            data={chartData}
            layout="vertical"
            margin={{ top: 5, right: 20, left: 10, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" horizontal={false} />
            <XAxis
              type="number"
              tick={{ fill: '#9ca3af', fontSize: 11 }}
              axisLine={{ stroke: '#475569' }}
              tickLine={false}
              tickFormatter={(v) => fmtVal(v)}
            />
            <YAxis
              type="category"
              dataKey="name"
              tick={{ fill: '#d1d5db', fontSize: 11 }}
              axisLine={{ stroke: '#475569' }}
              tickLine={false}
              width={130}
              tickFormatter={(label) => truncateLabel(label)}
            />
            <Tooltip
              content={<CustomLeaderboardTooltip fmtVal={fmtVal} valueLabel={valueLabel} />}
              cursor={{ fill: 'rgba(99, 102, 241, 0.1)' }}
            />
            <Bar
              dataKey="value"
              radius={[0, 4, 4, 0]}
              onClick={(data: any) => onBarClick?.(data.userId)}
              style={{ cursor: onBarClick ? 'pointer' : 'default' }}
            >
              {chartData.map((_, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={color}
                  fillOpacity={1 - index * 0.06}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
