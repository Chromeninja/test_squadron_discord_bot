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
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 sm:p-4">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs sm:text-sm font-medium text-gray-400 leading-tight">{label}</span>
        {icon && <span className="text-base sm:text-lg">{icon}</span>}
      </div>
      <div className="text-2xl sm:text-[1.7rem] font-bold text-white leading-tight">{value}</div>
      {subtitle && (
        <p className="text-[11px] sm:text-xs text-gray-500 mt-1 leading-tight">{subtitle}</p>
      )}
    </div>
  );
}
