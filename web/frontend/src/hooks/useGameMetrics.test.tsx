import '@testing-library/jest-dom';
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { isCancel, getGameMetrics } = vi.hoisted(() => ({
  isCancel: vi.fn(() => false),
  getGameMetrics: vi.fn(),
}));

vi.mock('axios', () => ({
  default: {
    isCancel,
  },
}));

vi.mock('../api/endpoints', () => ({
  metricsApi: {
    getGameMetrics,
  },
}));

import { useGameMetrics } from './useGameMetrics';

function deferred<T>(): {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason?: unknown) => void;
} {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('useGameMetrics', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    isCancel.mockReturnValue(false);
  });

  it('fetches game metrics and exposes the loaded data', async () => {
    getGameMetrics.mockResolvedValue({
      data: {
        game_name: 'Star Citizen',
        days: 30,
        total_seconds: 7200,
        session_count: 3,
        avg_seconds: 2400,
        unique_players: 2,
        top_players: [],
        timeseries: [],
      },
    });

    const { result } = renderHook(() =>
      useGameMetrics({
        gameName: 'Star Citizen',
        days: 30,
        dimension: 'voice',
        tier: 'regular',
        enabled: true,
      }),
    );

    await waitFor(() => {
      expect(result.current.gameMetricsLoading).toBe(false);
      expect(result.current.gameMetrics?.game_name).toBe('Star Citizen');
    });

    expect(getGameMetrics).toHaveBeenCalledWith(
      'Star Citizen',
      30,
      5,
      'voice',
      'regular',
      expect.any(AbortSignal),
    );
    expect(result.current.gameMetricsError).toBeNull();
  });

  it('resets state and skips fetching when disabled or missing a game name', async () => {
    const { result, rerender } = renderHook(
      ({ gameName, enabled }: { gameName: string | null; enabled: boolean }) =>
        useGameMetrics({
          gameName,
          enabled,
        }),
      {
        initialProps: { gameName: 'Star Citizen', enabled: true },
      },
    );

    await waitFor(() => {
      expect(getGameMetrics).toHaveBeenCalledTimes(1);
    });

    rerender({ gameName: null, enabled: false });

    await waitFor(() => {
      expect(result.current.gameMetrics).toBeNull();
      expect(result.current.gameMetricsError).toBeNull();
      expect(result.current.gameMetricsLoading).toBe(false);
    });

    expect(getGameMetrics).toHaveBeenCalledTimes(1);
  });

  it('exposes an error message for non-cancel failures and refetches on demand', async () => {
    getGameMetrics.mockRejectedValueOnce(new Error('boom')).mockResolvedValueOnce({
      data: {
        game_name: 'Star Citizen',
        days: 30,
        total_seconds: 3600,
        session_count: 1,
        avg_seconds: 3600,
        unique_players: 1,
        top_players: [],
        timeseries: [],
      },
    });

    const { result } = renderHook(() =>
      useGameMetrics({
        gameName: 'Star Citizen',
        days: 30,
      }),
    );

    await waitFor(() => {
      expect(result.current.gameMetricsError).toBe(
        'Metrics are currently unavailable for this game.',
      );
    });

    await act(async () => {
      result.current.refetch();
    });

    await waitFor(() => {
      expect(result.current.gameMetrics?.total_seconds).toBe(3600);
      expect(result.current.gameMetricsError).toBeNull();
    });
  });

  it('keeps only the newest response when requests overlap', async () => {
    const firstRequest = deferred<{
      data: {
        game_name: string;
        days: number;
        total_seconds: number;
        session_count: number;
        avg_seconds: number;
        unique_players: number;
        top_players: never[];
        timeseries: never[];
      };
    }>();
    const secondRequest = deferred<{
      data: {
        game_name: string;
        days: number;
        total_seconds: number;
        session_count: number;
        avg_seconds: number;
        unique_players: number;
        top_players: never[];
        timeseries: never[];
      };
    }>();

    getGameMetrics
      .mockReturnValueOnce(firstRequest.promise)
      .mockReturnValueOnce(secondRequest.promise);

    const { result, rerender } = renderHook(
      ({ gameName }: { gameName: string }) =>
        useGameMetrics({
          gameName,
          days: 30,
        }),
      {
        initialProps: { gameName: 'Old Game' },
      },
    );

    rerender({ gameName: 'New Game' });

    secondRequest.resolve({
      data: {
        game_name: 'New Game',
        days: 30,
        total_seconds: 9000,
        session_count: 4,
        avg_seconds: 2250,
        unique_players: 3,
        top_players: [],
        timeseries: [],
      },
    });
    firstRequest.resolve({
      data: {
        game_name: 'Old Game',
        days: 30,
        total_seconds: 1200,
        session_count: 1,
        avg_seconds: 1200,
        unique_players: 1,
        top_players: [],
        timeseries: [],
      },
    });

    await waitFor(() => {
      expect(result.current.gameMetrics?.game_name).toBe('New Game');
    });

    expect(result.current.gameMetrics?.total_seconds).toBe(9000);
  });
});