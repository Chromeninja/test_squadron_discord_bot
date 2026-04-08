import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const { useUserMetrics } = vi.hoisted(() => ({
  useUserMetrics: vi.fn(),
}));

vi.mock('../../hooks/useUserMetrics', () => ({
  useUserMetrics,
}));

vi.mock('../metrics/UserMetricsPanel', () => ({
  UserMetricsPanel: ({ metrics }: { metrics: { username?: string | null } | null }) => (
    <div>Shared metrics panel {metrics?.username ?? 'unknown'}</div>
  ),
}));

import UserDetailPanel from './UserDetailPanel';

describe('UserDetailPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useUserMetrics).mockReturnValue({
      userMetrics: {
        user_id: '123456789',
        username: 'PilotOne',
        total_messages: 10,
        total_voice_seconds: 3600,
        avg_messages_per_day: 1,
        avg_voice_per_day: 120,
        top_games: [],
        timeseries: [],
      },
      userMetricsLoading: false,
      userMetricsError: null,
      refetch: vi.fn(),
    });
  });

  it('uses the shared user metrics hook and panel', () => {
    render(
      <UserDetailPanel
        userId="123456789"
        username="PilotOne"
        days={30}
        onClose={() => {}}
      />,
    );

    expect(useUserMetrics).toHaveBeenCalledWith({
      userId: '123456789',
      days: 30,
      enabled: true,
    });
    expect(screen.getByText('User Metrics — PilotOne')).toBeInTheDocument();
    expect(screen.getByText('Shared metrics panel PilotOne')).toBeInTheDocument();
  });
});