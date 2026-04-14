import '@testing-library/jest-dom';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Outlet } from 'react-router-dom';

const { useAuth, authApi } = vi.hoisted(() => ({
  useAuth: vi.fn(),
  authApi: {
    selectGuild: vi.fn(),
  },
}));

vi.mock('./contexts/AuthContext', () => ({
  useAuth,
}));

vi.mock('./api/endpoints', () => ({
  authApi,
}));

vi.mock('./components/layout/DashboardShell', () => ({
  DashboardShell: () => <Outlet />,
}));

vi.mock('./pages/Dashboard', () => ({
  default: () => <div>Dashboard Page</div>,
}));
vi.mock('./pages/Users', () => ({
  default: () => <div>Users Page</div>,
}));
vi.mock('./pages/Voice', () => ({
  default: () => <div>Voice Page</div>,
}));
vi.mock('./pages/Metrics', () => ({
  default: () => <div>Metrics Page</div>,
}));
vi.mock('./pages/SelectServer', () => ({
  default: () => <div>Select Server Page</div>,
}));
vi.mock('./pages/DashboardBotSettings', () => ({
  default: () => <div>Settings Page</div>,
}));
vi.mock('./pages/Tickets', () => ({
  default: () => <div>Tickets Page</div>,
}));
vi.mock('./pages/Events', () => ({
  default: () => <div>Events Page</div>,
}));
vi.mock('./pages/EventEditor', () => ({
  default: () => <div>Event Editor Page</div>,
}));
vi.mock('./pages/EventDrafts', () => ({
  default: () => <div>Drafts Page</div>,
}));
vi.mock('./pages/EventRecurring', () => ({
  default: () => <div>Recurring Page</div>,
}));
vi.mock('./pages/Landing', () => ({
  default: ({ loginHref, user }: { loginHref: string; user: { user_id?: string } | null }) => (
    <div>
      <a href={loginHref}>Login with Discord</a>
      <span>{user ? 'Landing Authenticated' : 'Landing Anonymous'}</span>
    </div>
  ),
}));

import App from './App';

function buildUser(activeGuildId: string | null) {
  return {
    user_id: '42',
    username: 'Test User',
    discriminator: '0001',
    avatar: null,
    active_guild_id: activeGuildId,
    is_admin: false,
    is_moderator: false,
    is_bot_owner: false,
    authorized_guilds: {
      '123': {
        guild_id: '123',
        role_level: 'discord_manager' as const,
        source: 'test',
      },
    },
  };
}

describe('App routing', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('preserves current path in login URL for unauthenticated users', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: null,
      loading: false,
      setUser: vi.fn(),
      refreshProfile: vi.fn(),
      activeGuildId: null,
      userHasPermission: vi.fn(),
      getUserRoleLevel: vi.fn(),
    });

    render(
      <MemoryRouter initialEntries={['/dashboard/123/metrics?days=30']}>
        <App />
      </MemoryRouter>
    );

    const loginLink = await screen.findByRole('link', { name: 'Login with Discord' });
    expect(loginLink).toHaveAttribute(
      'href',
      '/auth/login?next=%2Fdashboard%2F123%2Fmetrics%3Fdays%3D30'
    );
  });

  it('redirects legacy metrics route to guild-scoped metrics route', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: buildUser('123'),
      loading: false,
      setUser: vi.fn(),
      refreshProfile: vi.fn(async () => {}),
      activeGuildId: '123',
      userHasPermission: vi.fn(() => true),
      getUserRoleLevel: vi.fn(() => 'discord_manager'),
    });

    render(
      <MemoryRouter initialEntries={['/metrics']}>
        <App />
      </MemoryRouter>
    );

    expect(await screen.findByText('Metrics Page')).toBeInTheDocument();
  });

  it('auto-selects requested guild when opening guild-scoped deep link', async () => {
    let currentUser = buildUser(null);
    const refreshProfile = vi.fn(async () => {
      currentUser = buildUser('123');
    });

    vi.mocked(authApi.selectGuild).mockResolvedValue({ success: true });
    vi.mocked(useAuth).mockImplementation(() => ({
      user: currentUser,
      loading: false,
      setUser: vi.fn(),
      refreshProfile,
      activeGuildId: currentUser.active_guild_id,
      userHasPermission: vi.fn(() => true),
      getUserRoleLevel: vi.fn(() => 'discord_manager'),
    }));

    render(
      <MemoryRouter initialEntries={['/dashboard/123/metrics']}>
        <App />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(authApi.selectGuild).toHaveBeenCalledWith('123');
    });
    expect(refreshProfile).toHaveBeenCalled();
  });

  it('allows authenticated users to open the public home route', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: buildUser('123'),
      loading: false,
      setUser: vi.fn(),
      refreshProfile: vi.fn(async () => {}),
      activeGuildId: '123',
      userHasPermission: vi.fn(() => true),
      getUserRoleLevel: vi.fn(() => 'discord_manager'),
    });

    render(
      <MemoryRouter initialEntries={['/home']}>
        <App />
      </MemoryRouter>
    );

    expect(await screen.findByText('Landing Authenticated')).toBeInTheDocument();
  });
});
