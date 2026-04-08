/**
 * useUserMetrics — Shared hook for fetching per-user metrics.
 *
 * Encapsulates the metrics-fetching logic previously duplicated across
 * Users.tsx and Voice.tsx.  The hook is triggered when `userId` is
 * non-null and `enabled` is true, and automatically resets when those
 * inputs change.
 */

import axios from 'axios';
import { useCallback, useEffect, useRef, useState } from 'react';
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
  const abortControllerRef = useRef<AbortController | null>(null);
  const requestSequenceRef = useRef(0);

  const fetchMetrics = useCallback(() => {
    abortControllerRef.current?.abort();

    if (!userId || !enabled) {
      setUserMetrics(null);
      setUserMetricsError(null);
      setUserMetricsLoading(false);
      return;
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;
    const requestId = requestSequenceRef.current + 1;
    requestSequenceRef.current = requestId;

    setUserMetrics(null);
    setUserMetricsError(null);
    setUserMetricsLoading(true);

    metricsApi
      .getUserMetrics(userId, days, controller.signal)
      .then((resp) => {
        if (!controller.signal.aborted && requestId === requestSequenceRef.current) {
          setUserMetrics(resp.data);
        }
      })
      .catch((error) => {
        if (axios.isCancel(error) || controller.signal.aborted) {
          return;
        }
        if (requestId === requestSequenceRef.current) {
          setUserMetrics(null);
          setUserMetricsError('Metrics are currently unavailable for this member.');
        }
      })
      .finally(() => {
        if (!controller.signal.aborted && requestId === requestSequenceRef.current) {
          setUserMetricsLoading(false);
        }
      });

    return () => {
      controller.abort();
    };
  }, [userId, days, enabled]);

  useEffect(() => {
    const cleanup = fetchMetrics();
    return cleanup;
  }, [fetchMetrics]);

  const refetch = useCallback(() => {
    fetchMetrics();
  }, [fetchMetrics]);

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  return { userMetrics, userMetricsLoading, userMetricsError, refetch };
}
