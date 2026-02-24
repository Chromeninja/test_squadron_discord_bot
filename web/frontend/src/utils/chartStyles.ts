/**
 * Shared chart tooltip / styling constants.
 *
 * Keeps the Recharts dark-theme tooltip appearance consistent across
 * TimeSeriesChart, LeaderboardChart, GamePieChart, and UserDetailPanel.
 */

import type { CSSProperties } from 'react';

/** Standard dark-slate tooltip style for Recharts `<Tooltip contentStyle={…} />`. */
export const CHART_TOOLTIP_STYLE: CSSProperties = {
  backgroundColor: '#1e293b',
  border: '1px solid #334155',
  borderRadius: '6px',
  padding: '8px 12px',
  fontSize: '12px',
  color: '#e2e8f0',
};
