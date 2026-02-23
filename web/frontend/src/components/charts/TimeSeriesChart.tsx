/**
 * TimeSeriesChart — Line/Area chart for messages or voice time-series data.
 *
 * Wraps Recharts with dark-theme styling matching the slate/gray palette.
 */

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

interface DataPoint {
  timestamp: number;
  value?: number;
  unique_users?: number;
}

interface TimeSeriesChartProps {
  data: DataPoint[];
  title: string;
  color?: string;
  /** Label for the value axis */
  valueLabel?: string;
  /** Format function for values (e.g., convert seconds to hours) */
  formatValue?: (val: number) => string;
}

function formatTimestamp(epoch: number): string {
  const d = new Date(epoch * 1000);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

export default function TimeSeriesChart({
  data,
  title,
  color = '#6366f1',
  valueLabel = 'Value',
  formatValue,
}: TimeSeriesChartProps) {
  // Aggregate hourly data to daily for cleaner display
  const dailyMap = new Map<string, { timestamp: number; value: number; unique_users: number }>();
  for (const point of data) {
    const dayKey = formatTimestamp(point.timestamp);
    const existing = dailyMap.get(dayKey);
    if (existing) {
      existing.value += point.value ?? 0;
      existing.unique_users = Math.max(existing.unique_users, point.unique_users ?? 0);
    } else {
      dailyMap.set(dayKey, {
        timestamp: point.timestamp,
        value: point.value ?? 0,
        unique_users: point.unique_users ?? 0,
      });
    }
  }

  const chartData = Array.from(dailyMap.entries()).map(([day, d]) => ({
    day,
    value: d.value,
    unique_users: d.unique_users,
  }));

  const fmtVal = formatValue ?? ((v: number) => v.toLocaleString());

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
      <h3 className="text-sm font-semibold text-gray-300 mb-4">{title}</h3>
      {chartData.length === 0 ? (
        <div className="flex items-center justify-center h-48 text-gray-500 text-sm">
          No data available for this period
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <AreaChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <defs>
              <linearGradient id={`gradient-${color.replace('#', '')}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={color} stopOpacity={0.3} />
                <stop offset="95%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis
              dataKey="day"
              tick={{ fill: '#9ca3af', fontSize: 11 }}
              axisLine={{ stroke: '#475569' }}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: '#9ca3af', fontSize: 11 }}
              axisLine={{ stroke: '#475569' }}
              tickLine={false}
              tickFormatter={(v) => fmtVal(v)}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1e293b',
                border: '1px solid #334155',
                borderRadius: '6px',
                color: '#e2e8f0',
                fontSize: '12px',
              }}
              formatter={(value: number | undefined) => [fmtVal(value ?? 0), valueLabel]}
              labelFormatter={(label) => label}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke={color}
              strokeWidth={2}
              fill={`url(#gradient-${color.replace('#', '')})`}
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
