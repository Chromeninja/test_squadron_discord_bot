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

/** Custom tooltip that includes unique_users count when available. */
function CustomTimeSeriesToolip({ active, payload, label, fmtVal, valueLabel }: any) {
  if (!active || !payload || payload.length === 0) return null;
  const entry = payload[0]?.payload;
  if (!entry) return null;
  const value = entry.value ?? 0;
  const users = entry.unique_users ?? 0;
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
      <div className="font-medium text-white mb-1">{label}</div>
      <div className="text-gray-300">
        {valueLabel}: {fmtVal(value)}
      </div>
      {users > 0 && (
        <div className="text-gray-400 text-[11px]">
          {users} unique user{users !== 1 ? 's' : ''}
        </div>
      )}
    </div>
  );
}

/** Compute a reasonable tick interval for the X-axis based on data point count. */
function getTickInterval(dataLength: number): number | 'preserveStartEnd' {
  if (dataLength <= 14) return 0;         // show all labels for ≤14 days
  if (dataLength <= 35) return 1;         // every other label
  if (dataLength <= 60) return 4;         // ~weekly
  return Math.floor(dataLength / 10);     // ~10 labels for 90d+
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
  const tickInterval = getTickInterval(chartData.length);

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-5" role="img" aria-label={`${title} trend chart`}>
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
              interval={tickInterval}
            />
            <YAxis
              tick={{ fill: '#9ca3af', fontSize: 11 }}
              axisLine={{ stroke: '#475569' }}
              tickLine={false}
              tickFormatter={(v) => fmtVal(v)}
            />
            <Tooltip
              content={<CustomTimeSeriesToolip fmtVal={fmtVal} valueLabel={valueLabel} />}
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
