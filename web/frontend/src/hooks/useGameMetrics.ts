import axios from 'axios';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityDimension,
  ActivityTier,
  GameMetricsDetail,
  metricsApi,
} from '../api/endpoints';
import { useRequestSequence } from './useRequestSequence';

interface UseGameMetricsOptions {
  gameName: string | null;
  days?: number;
  dimension?: ActivityDimension | ActivityDimension[];
  tier?: ActivityTier | ActivityTier[];
  enabled?: boolean;
}

interface UseGameMetricsResult {
  gameMetrics: GameMetricsDetail | null;
  gameMetricsLoading: boolean;
  gameMetricsError: string | null;
  refetch: () => void;
}

export function useGameMetrics({
  gameName,
  days = 30,
  dimension,
  tier,
  enabled = true,
}: UseGameMetricsOptions): UseGameMetricsResult {
  const [gameMetrics, setGameMetrics] = useState<GameMetricsDetail | null>(null);
  const [gameMetricsLoading, setGameMetricsLoading] = useState(false);
  const [gameMetricsError, setGameMetricsError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const requestSequence = useRequestSequence();

  const fetchMetrics = useCallback(() => {
    abortControllerRef.current?.abort();

    if (!gameName || !enabled) {
      setGameMetrics(null);
      setGameMetricsError(null);
      setGameMetricsLoading(false);
      return;
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;
    const requestId = requestSequence.next();

    setGameMetrics(null);
    setGameMetricsError(null);
    setGameMetricsLoading(true);

    metricsApi
      .getGameMetrics(gameName, days, 5, dimension, tier, controller.signal)
      .then((response) => {
        if (!controller.signal.aborted && requestSequence.isCurrent(requestId)) {
          setGameMetrics(response.data);
        }
      })
      .catch((error) => {
        if (axios.isCancel(error) || controller.signal.aborted) {
          return;
        }
        if (requestSequence.isCurrent(requestId)) {
          setGameMetrics(null);
          setGameMetricsError('Metrics are currently unavailable for this game.');
        }
      })
      .finally(() => {
        if (!controller.signal.aborted && requestSequence.isCurrent(requestId)) {
          setGameMetricsLoading(false);
        }
      });

    return () => {
      controller.abort();
    };
  }, [days, dimension, enabled, gameName, tier, requestSequence]);

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

  return { gameMetrics, gameMetricsLoading, gameMetricsError, refetch };
}