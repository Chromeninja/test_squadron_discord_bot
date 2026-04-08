import '@testing-library/jest-dom';
import { act, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { metricsApi, handleApiError } = vi.hoisted(() => ({
  metricsApi: {
    getDashboardBundle: vi.fn(),
    getOverview: vi.fn(),
    getVoiceLeaderboard: vi.fn(),
    getMessageLeaderboard: vi.fn(),
    getTopGames: vi.fn(),
    getTimeSeries: vi.fn(),
    getActivityGroups: vi.fn(),
  },
  handleApiError: vi.fn(),
}));

vi.mock('../api/endpoints', () => ({
  metricsApi,
}));

vi.mock('../hooks/useClickOutside', () => ({
  useClickOutside: vi.fn(),
}));

vi.mock('../utils/toast', () => ({
  handleApiError,
}));

vi.mock('../components/charts', () => ({
  MetricCard: ({ label, value }: { label: string; value: string }) => (
    <div>{label}: {value}</div>
  ),
  TimeSeriesChart: ({ title }: { title: string }) => <div>{title}</div>,
  LeaderboardChart: ({ title }: { title: string }) => <div>{title}</div>,
  GamePieChart: ({ title }: { title: string }) => <div>{title}</div>,
  UserDetailPanel: () => null,
  GameDetailPanel: () => null,
}));

import Metrics from './Metrics';

async function waitForDebouncedLoad(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => window.setTimeout(resolve, 350));
  });
}

function createBundleResponse() {
  return {
    success: true,
    data: {
      overview: {
        live: {
          messages_today: 42,
          active_voice_users: 3,
          active_game_sessions: 5,
          top_game: 'Star Citizen',
        },
        period: {
          total_messages: 1200,
          unique_messagers: 25,
          avg_messages_per_user: 48,
          total_voice_seconds: 360000,
          unique_voice_users: 18,
          avg_voice_per_user: 20000,
          unique_users: 30,
          top_games: [],
        },
      },
      voice_leaderboard: [
        { user_id: '123456789', total_seconds: 7200, username: 'PilotOne' },
      ],
      message_leaderboard: [
        { user_id: '123456789', total_messages: 500, username: 'PilotOne' },
      ],
      top_games: [
        {
          game_name: 'Star Citizen',
          total_seconds: 72000,
          session_count: 20,
          avg_seconds: 3600,
          unique_players: 10,
        },
      ],
      message_timeseries: [
        { timestamp: 1735689600, value: 10, unique_users: 2 },
      ],
      voice_timeseries: [
        { timestamp: 1735689600, value: 3600, unique_users: 2 },
      ],
      activity_counts: {
        all: { hardcore: 2, regular: 5, casual: 8, reserve: 10, inactive: 25 },
        voice: { hardcore: 2, regular: 5, casual: 8, reserve: 10, inactive: 25 },
        chat: { hardcore: 2, regular: 5, casual: 8, reserve: 10, inactive: 25 },
        game: { hardcore: 2, regular: 5, casual: 8, reserve: 10, inactive: 25 },
      },
    },
  };
}

describe('Metrics Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
    metricsApi.getDashboardBundle.mockResolvedValue(createBundleResponse());
  });

  it('loads metrics through the bundled endpoint', async () => {
    render(<Metrics />);

    await waitForDebouncedLoad();

    await waitFor(() => {
      expect(metricsApi.getDashboardBundle).toHaveBeenCalledTimes(1);
    });

    expect(metricsApi.getOverview).not.toHaveBeenCalled();
    expect(metricsApi.getVoiceLeaderboard).not.toHaveBeenCalled();
    expect(metricsApi.getMessageLeaderboard).not.toHaveBeenCalled();
    expect(metricsApi.getTopGames).not.toHaveBeenCalled();
    expect(metricsApi.getTimeSeries).not.toHaveBeenCalled();
    expect(metricsApi.getActivityGroups).not.toHaveBeenCalled();
    expect(screen.getByText('Total Messages: 1,200')).toBeInTheDocument();
    expect(screen.getByText(/Server Metrics/i)).toBeInTheDocument();
  });

  it('shows an error state when the bundled request fails', async () => {
    metricsApi.getDashboardBundle.mockRejectedValue(new Error('boom'));

    render(<Metrics />);

    await waitForDebouncedLoad();

    await waitFor(() => {
      expect(screen.getByText('Failed to load metrics data')).toBeInTheDocument();
    });

    expect(handleApiError).toHaveBeenCalled();
  });
});