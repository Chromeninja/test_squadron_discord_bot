import '@testing-library/jest-dom';
import { render, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { usersApi, adminApi, useAuth } = vi.hoisted(() => ({
  usersApi: {
    getUsers: vi.fn(),
    getAvailableOrgs: vi.fn(),
    getUserDetails: vi.fn(),
    resolveFilteredIds: vi.fn(),
    exportUsers: vi.fn(),
  },
  adminApi: {
    bulkRecheckUsers: vi.fn(),
    startBulkRecheckUsers: vi.fn(),
    getBulkRecheckProgress: vi.fn(),
  },
  useAuth: vi.fn(),
}));

vi.mock('../api/endpoints', () => ({
  usersApi,
  adminApi,
  ALL_GUILDS_SENTINEL: '*',
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth,
}));

vi.mock('../utils/toast', () => ({
  handleApiError: vi.fn(),
}));

vi.mock('../components/BulkRecheckResultsModal', () => ({
  BulkRecheckResultsModal: () => null,
}));

vi.mock('../components/users/UserDetailsModal', () => ({
  UserDetailsModal: () => null,
}));

vi.mock('../components/users/OrgBadgeList', () => ({
  OrgBadgeList: () => null,
}));

import Users from './Users';

function createUser(activeGuildId: string = '987654321') {
  return {
    user_id: '123456789',
    username: 'TestUser',
    discriminator: '0',
    avatar: null,
    active_guild_id: activeGuildId,
    authorized_guilds: {
      [activeGuildId]: {
        guild_id: activeGuildId,
        role_level: 'moderator' as const,
        source: 'test',
      },
    },
  };
}

describe('Users Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue({
      user: createUser(),
      activeGuildId: '987654321',
      loading: false,
    });
    vi.mocked(usersApi.getAvailableOrgs).mockResolvedValue({
      success: true,
      orgs: ['TEST', 'CIC'],
    });
    vi.mocked(usersApi.getUsers).mockResolvedValue({
      success: true,
      items: [],
      total: 0,
      page: 1,
      page_size: 25,
      total_pages: 0,
      is_cross_guild: false,
    });
  });

  it('loads users from auth context and fetches org options once', async () => {
    render(<Users />);

    await waitFor(() => {
      expect(usersApi.getUsers).toHaveBeenCalledTimes(1);
    });

    expect(usersApi.getAvailableOrgs).toHaveBeenCalledTimes(1);
  });

  it('does not refetch org options when the active guild changes', async () => {
    const { rerender } = render(<Users />);

    await waitFor(() => {
      expect(usersApi.getAvailableOrgs).toHaveBeenCalledTimes(1);
    });

    vi.mocked(useAuth).mockReturnValue({
      user: createUser('123123123'),
      activeGuildId: '123123123',
      loading: false,
    });

    rerender(<Users />);

    await waitFor(() => {
      expect(usersApi.getUsers).toHaveBeenCalled();
    });

    expect(usersApi.getAvailableOrgs).toHaveBeenCalledTimes(1);
  });
});