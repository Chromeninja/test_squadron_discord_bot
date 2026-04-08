import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const { useGameMetrics } = vi.hoisted(() => ({
  useGameMetrics: vi.fn(),
}));

vi.mock('../../hooks/useGameMetrics', () => ({
  useGameMetrics,
}));

import GameDetailPanel from './GameDetailPanel';

describe('GameDetailPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useGameMetrics).mockReturnValue({
      gameMetrics: {
        game_name: 'Star Citizen',
        days: 30,
        total_seconds: 7200,
        session_count: 3,
        avg_seconds: 2400,
        unique_players: 2,
        top_players: [
          {
            user_id: '123456789',
            total_seconds: 3600,
            session_count: 2,
            avg_seconds: 1800,
            username: 'PilotOne',
          },
        ],
        timeseries: [],
      },
      gameMetricsLoading: false,
      gameMetricsError: null,
      refetch: vi.fn(),
    });
  });

  it('uses the shared game metrics hook', () => {
    render(
      <GameDetailPanel
        gameName="Star Citizen"
        days={30}
        dimension="voice"
        tier="regular"
        onClose={() => {}}
      />,
    );

    expect(useGameMetrics).toHaveBeenCalledWith({
      gameName: 'Star Citizen',
      days: 30,
      dimension: 'voice',
      tier: 'regular',
      enabled: true,
    });
    expect(screen.getByText(/Game Metrics/i)).toBeInTheDocument();
    expect(screen.getByText('PilotOne')).toBeInTheDocument();
  });
});