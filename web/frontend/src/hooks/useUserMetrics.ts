/**
 * useUserMetrics — Shared hook for fetching per-user metrics.
 *
 * Encapsulates the metrics-fetching logic previously duplicated across
 * Users.tsx and Voice.tsx.  The hook is triggered when `userId` is
 * non-null and `enabled` is true, and automatically resets when those
 * inputs change.
 */

import { useCallback, useEffect, useState } from 'react';
import { metricsApi, UserMetrics } from '../api/endpoints';

interface UseUserMetricsOptions {
  /** Discord user ID to fetch metrics for. Pass `null` to skip. */
  userId: string | null;
  /** Number of lookback days (default: 30). */
  days?: number;
  /** Gate flag — set to `false` to suppress the fetch (e.g. cross-guild mode). */
  enabled?: boolean;
}

interface UseUserMetricsResult {
  userMetrics: UserMetrics | null;
  userMetricsLoading: boolean;
  userMetricsError: string | null;
  /** Force a refetch with the current parameters. */
  refetch: () => void;
}

export function useUserMetrics({
  userId,
  days = 30,
  enabled = true,
}: UseUserMetricsOptions): UseUserMetricsResult {
  const [userMetrics, setUserMetrics] = useState<UserMetrics | null>(null);
  const [userMetricsLoading, setUserMetricsLoading] = useState(false);
  const [userMetricsError, setUserMetricsError] = useState<string | null>(null);

  const fetchMetrics = useCallback(() => {
    if (!userId || !enabled) {
      setUserMetrics(null);
      setUserMetricsError(null);
      setUserMetricsLoading(false);
      return;
    }

    let cancelled = false;
    setUserMetrics(null);
    setUserMetricsError(null);
    setUserMetricsLoading(true);

    metricsApi
      .getUserMetrics(userId, days)
      .then((resp) => {
        if (!cancelled) setUserMetrics(resp.data);
      })
      .catch(() => {
        if (!cancelled) {
          setUserMetrics(null);
          setUserMetricsError('Metrics are currently unavailable for this member.');
        }
      })
      .finally(() => {
        if (!cancelled) setUserMetricsLoading(false);
      });

    // Return cleanup for the effect
    return () => {
      cancelled = true;
    };
  }, [userId, days, enabled]);

  useEffect(() => {
    const cleanup = fetchMetrics();
    return cleanup;
  }, [fetchMetrics]);

  const refetch = useCallback(() => {
    fetchMetrics();
  }, [fetchMetrics]);

  return { userMetrics, userMetricsLoading, userMetricsError, refetch };
}
