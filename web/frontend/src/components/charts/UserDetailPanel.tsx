/**
 * UserDetailPanel — Expandable panel showing per-user metrics breakdown.
 *
 * Displayed when clicking a user in a leaderboard chart.
 */

import { useEffect } from 'react';
import { UserMetricsPanel } from '../metrics/UserMetricsPanel';
import { useUserMetrics } from '../../hooks/useUserMetrics';

interface UserDetailPanelProps {
  userId: string;
  username?: string | null;
  days: number;
  onClose: () => void;
}

export default function UserDetailPanel({ userId, username, days, onClose }: UserDetailPanelProps) {
  const {
    userMetrics,
    userMetricsLoading,
    userMetricsError,
    refetch,
  } = useUserMetrics({
    userId,
    days,
    enabled: true,
  });

  // Close modal on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      role="dialog"
      aria-modal="true"
      aria-label={`User metrics for ${username || userId}`}
    >
      <div className="bg-slate-800 border border-slate-700 rounded-xl max-w-2xl w-full max-h-[85vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700">
          <div className="flex items-center gap-4 flex-wrap">
            <h3 className="text-lg font-semibold text-white">
              User Metrics — {(userMetrics?.username?.trim() || username?.trim()) ? (userMetrics?.username?.trim() || username?.trim()) : `${userId.slice(-8)}…`}
            </h3>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition text-xl leading-none"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="p-6">
          {userMetricsError ? (
            <div className="flex flex-col items-center justify-center h-48 gap-3">
              <p className="text-red-400 text-sm">{userMetricsError}</p>
              <button
                onClick={refetch}
                className="px-4 py-2 bg-red-700 text-white rounded hover:bg-red-600 transition text-sm"
              >
                Retry
              </button>
            </div>
          ) : (
            <UserMetricsPanel
              metrics={userMetrics}
              loading={userMetricsLoading}
              error={null}
              days={days}
              showChart={true}
            />
          )}
        </div>
      </div>
    </div>
  );
}
