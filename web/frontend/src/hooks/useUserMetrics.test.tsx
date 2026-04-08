import '@testing-library/jest-dom';
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { isCancel, getUserMetrics } = vi.hoisted(() => ({
  isCancel: vi.fn(() => false),
  getUserMetrics: vi.fn(),
}));

vi.mock('axios', () => ({
  default: {
    isCancel,
  },
}));

vi.mock('../api/endpoints', () => ({
  metricsApi: {
    getUserMetrics,
  },
}));

import { useUserMetrics } from './useUserMetrics';

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

describe('useUserMetrics', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    isCancel.mockReturnValue(false);
  });

  it('fetches user metrics and exposes the loaded data', async () => {
    getUserMetrics.mockResolvedValue({
      data: {
        user_id: '123',
        username: 'PilotOne',
        total_messages: 10,
        total_voice_seconds: 3600,
        avg_messages_per_day: 1,
        avg_voice_per_day: 120,
        top_games: [],
        timeseries: [],
      },
    });

    const { result } = renderHook(() =>
      useUserMetrics({
        userId: '123',
        days: 30,
        enabled: true,
      }),
    );

    await waitFor(() => {
      expect(result.current.userMetricsLoading).toBe(false);
      expect(result.current.userMetrics?.username).toBe('PilotOne');
    });

    expect(getUserMetrics).toHaveBeenCalledWith('123', 30, expect.any(AbortSignal));
    expect(result.current.userMetricsError).toBeNull();
  });

  it('clears state and skips fetching when the user is not enabled', async () => {
    const { result, rerender } = renderHook(
      ({ userId, enabled }: { userId: string | null; enabled: boolean }) =>
        useUserMetrics({
          userId,
          enabled,
        }),
      {
        initialProps: { userId: '123', enabled: true },
      },
    );

    await waitFor(() => {
      expect(getUserMetrics).toHaveBeenCalledTimes(1);
    });

    rerender({ userId: null, enabled: false });

    await waitFor(() => {
      expect(result.current.userMetrics).toBeNull();
      expect(result.current.userMetricsError).toBeNull();
      expect(result.current.userMetricsLoading).toBe(false);
    });

    expect(getUserMetrics).toHaveBeenCalledTimes(1);
  });

  it('shows an error for non-cancel failures and recovers on refetch', async () => {
    getUserMetrics.mockRejectedValueOnce(new Error('boom')).mockResolvedValueOnce({
      data: {
        user_id: '123',
        username: 'PilotOne',
        total_messages: 20,
        total_voice_seconds: 7200,
        avg_messages_per_day: 2,
        avg_voice_per_day: 240,
        top_games: [],
        timeseries: [],
      },
    });

    const { result } = renderHook(() =>
      useUserMetrics({
        userId: '123',
        days: 30,
      }),
    );

    await waitFor(() => {
      expect(result.current.userMetricsError).toBe(
        'Metrics are currently unavailable for this member.',
      );
    });

    await act(async () => {
      result.current.refetch();
    });

    await waitFor(() => {
      expect(result.current.userMetrics?.total_voice_seconds).toBe(7200);
      expect(result.current.userMetricsError).toBeNull();
    });
  });

  it('ignores stale responses when the selected user changes', async () => {
    const firstRequest = deferred<{
      data: {
        user_id: string;
        username: string;
        total_messages: number;
        total_voice_seconds: number;
        avg_messages_per_day: number;
        avg_voice_per_day: number;
        top_games: never[];
        timeseries: never[];
      };
    }>();
    const secondRequest = deferred<{
      data: {
        user_id: string;
        username: string;
        total_messages: number;
        total_voice_seconds: number;
        avg_messages_per_day: number;
        avg_voice_per_day: number;
        top_games: never[];
        timeseries: never[];
      };
    }>();

    getUserMetrics
      .mockReturnValueOnce(firstRequest.promise)
      .mockReturnValueOnce(secondRequest.promise);

    const { result, rerender } = renderHook(
      ({ userId }: { userId: string }) =>
        useUserMetrics({
          userId,
          days: 30,
        }),
      {
        initialProps: { userId: 'old-user' },
      },
    );

    rerender({ userId: 'new-user' });

    secondRequest.resolve({
      data: {
        user_id: 'new-user',
        username: 'New Pilot',
        total_messages: 12,
        total_voice_seconds: 4200,
        avg_messages_per_day: 1.5,
        avg_voice_per_day: 140,
        top_games: [],
        timeseries: [],
      },
    });
    firstRequest.resolve({
      data: {
        user_id: 'old-user',
        username: 'Old Pilot',
        total_messages: 2,
        total_voice_seconds: 1200,
        avg_messages_per_day: 0.5,
        avg_voice_per_day: 40,
        top_games: [],
        timeseries: [],
      },
    });

    await waitFor(() => {
      expect(result.current.userMetrics?.user_id).toBe('new-user');
    });

    expect(result.current.userMetrics?.username).toBe('New Pilot');
  });
});