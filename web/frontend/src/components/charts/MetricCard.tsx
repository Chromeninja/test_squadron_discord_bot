/**
 * MetricCard — Summary statistic card with label, value, and optional subtitle.
 *
 * Used in the metrics dashboard summary row for KPI-style numbers.
 */

interface MetricCardProps {
  label: string;
  value: string | number;
  subtitle?: string;
  icon?: string;
}

export default function MetricCard({ label, value, subtitle, icon }: MetricCardProps) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-gray-400">{label}</span>
        {icon && <span className="text-lg">{icon}</span>}
      </div>
      <div className="text-2xl font-bold text-white">{value}</div>
      {subtitle && (
        <p className="text-xs text-gray-500 mt-1">{subtitle}</p>
      )}
    </div>
  );
}
