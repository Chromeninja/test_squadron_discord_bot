import '@testing-library/jest-dom';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { statsApi, healthApi, errorsApi, logsApi, useAuth } = vi.hoisted(() => ({
  statsApi: {
    getOverview: vi.fn(),
  },
  healthApi: {
    getOverview: vi.fn(),
  },
  errorsApi: {
    getLast: vi.fn(),
  },
  logsApi: {
    exportLogs: vi.fn(),
    exportBackendLogs: vi.fn(),
    exportAuditLogs: vi.fn(),
  },
  useAuth: vi.fn(),
}));

vi.mock('../api/endpoints', () => ({
  statsApi,
  healthApi,
  errorsApi,
  logsApi,
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth,
}));

vi.mock('../utils/toast', () => ({
  handleApiError: vi.fn(),
  showSuccess: vi.fn(),
}));

import Dashboard from './Dashboard';

function createUser(roleLevel: 'staff' | 'bot_admin' = 'bot_admin') {
  return {
    user_id: '123456789',
    username: 'TestUser',
    discriminator: '0',
    avatar: null,
    active_guild_id: '987654321',
    is_admin: false,
    is_bot_owner: false,
    authorized_guilds: {
      '987654321': {
        guild_id: '987654321',
        role_level: roleLevel,
        source: 'test',
      },
    },
  };
}

describe('Dashboard Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue({ user: createUser(), loading: false });
    vi.mocked(statsApi.getOverview).mockResolvedValue({
      success: true,
      data: {
        total_verified: 42,
        by_status: { main: 10, affiliate: 5, non_member: 3, unknown: 1 },
        voice_active_count: 7,
      },
    });
    vi.mocked(healthApi.getOverview).mockResolvedValue({
      success: true,
      data: {
        status: 'healthy',
        uptime_seconds: 3600,
        db_ok: true,
        discord_latency_ms: 42,
        system: { cpu_percent: 12, memory_percent: 34 },
      },
    });
    vi.mocked(errorsApi.getLast).mockResolvedValue({
      success: true,
      errors: [],
    });
  });

  it('loads dashboard data using auth context without page-level auth fetches', async () => {
    render(<Dashboard />);

    await waitFor(() => {
      expect(statsApi.getOverview).toHaveBeenCalledTimes(1);
    });

    expect(healthApi.getOverview).toHaveBeenCalledTimes(1);
    expect(errorsApi.getLast).toHaveBeenCalledWith(1);
    expect(screen.getByText('Dashboard Overview')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
  });

  it('skips admin-only requests for non-admin users', async () => {
    vi.mocked(useAuth).mockReturnValue({ user: createUser('staff'), loading: false });

    render(<Dashboard />);

    await waitFor(() => {
      expect(statsApi.getOverview).toHaveBeenCalledTimes(1);
    });

    expect(healthApi.getOverview).not.toHaveBeenCalled();
    expect(errorsApi.getLast).not.toHaveBeenCalled();
  });
});