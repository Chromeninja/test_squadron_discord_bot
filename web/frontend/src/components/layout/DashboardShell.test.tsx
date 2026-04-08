import '@testing-library/jest-dom';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const { authApi, guildApi, useIsMobile } = vi.hoisted(() => ({
  authApi: {
    logout: vi.fn(),
    clearActiveGuild: vi.fn(),
    getGuilds: vi.fn(),
    selectGuild: vi.fn(),
  },
  guildApi: {
    getGuildConfig: vi.fn(),
    getGuildInfo: vi.fn(),
  },
  useIsMobile: vi.fn(),
}));

vi.mock('../../api/endpoints', () => ({
  ALL_GUILDS_SENTINEL: '*',
  authApi,
  guildApi,
}));

vi.mock('../../hooks/useMediaQuery', () => ({
  useIsMobile,
}));

import { DashboardShell } from './DashboardShell';

function createUser() {
  return {
    user_id: '444333222',
    username: 'Coordinator',
    discriminator: '0005',
    avatar: null,
    active_guild_id: '123',
    authorized_guilds: {
      '123': {
        guild_id: '123',
        role_level: 'event_coordinator' as const,
        source: 'event_coordinator_role',
      },
    },
  };
}

describe('DashboardShell Events Navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useIsMobile).mockReturnValue(false);
    vi.mocked(guildApi.getGuildConfig).mockResolvedValue({
      success: true,
      data: {
        events: {
          enabled: true,
          default_native_sync: true,
          default_announcement_channel_id: null,
          default_voice_channel_id: null,
        },
      },
    });
    vi.mocked(guildApi.getGuildInfo).mockResolvedValue({
      success: true,
      guild: {
        guild_id: '123',
        guild_name: 'TEST Squadron',
        icon_url: null,
      },
    });
    vi.mocked(authApi.getGuilds).mockResolvedValue({
      success: true,
      guilds: [
        {
          guild_id: '123',
          guild_name: 'TEST Squadron',
          icon_url: null,
        },
        {
          guild_id: '456',
          guild_name: 'RSI Ops',
          icon_url: null,
        },
      ],
    });
    vi.mocked(authApi.selectGuild).mockResolvedValue({ success: true });
  });

  it('shows the event workspace sidebar items when the event module is enabled', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route
            path="/"
            element={
              <DashboardShell
                user={createUser()}
                onUserChange={vi.fn()}
                onRefreshProfile={vi.fn(async () => {})}
              />
            }
          >
            <Route index element={<div>Dashboard Content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(guildApi.getGuildConfig).toHaveBeenCalledWith('123');
    });

    expect(screen.getByRole('link', { name: 'Events' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Drafts' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Recurring' })).toBeInTheDocument();
  });

  it('hides the event workspace sidebar items when the event module is disabled', async () => {
    vi.mocked(guildApi.getGuildConfig).mockResolvedValue({
      success: true,
      data: {
        events: {
          enabled: false,
          default_native_sync: true,
          default_announcement_channel_id: null,
          default_voice_channel_id: null,
        },
      },
    });

    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route
            path="/"
            element={
              <DashboardShell
                user={createUser()}
                onUserChange={vi.fn()}
                onRefreshProfile={vi.fn(async () => {})}
              />
            }
          >
            <Route index element={<div>Dashboard Content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(guildApi.getGuildConfig).toHaveBeenCalledWith('123');
    });

    expect(screen.queryByRole('link', { name: 'Events' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Drafts' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Recurring' })).not.toBeInTheDocument();
  });

  it('opens a workspace dropdown with available guilds', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route
            path="/"
            element={
              <DashboardShell
                user={createUser()}
                onUserChange={vi.fn()}
                onRefreshProfile={vi.fn(async () => {})}
              />
            }
          >
            <Route index element={<div>Dashboard Content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(authApi.getGuilds).toHaveBeenCalled();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Switch workspace' }));

    expect(screen.getByRole('menu', { name: 'Workspace options' })).toBeInTheDocument();
    expect(screen.getByRole('menuitemradio', { name: 'TEST Squadron' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
    expect(screen.getByRole('menuitemradio', { name: 'RSI Ops' })).toBeInTheDocument();
  });

  it('switches workspaces directly from the dropdown', async () => {
    const onRefreshProfile = vi.fn(async () => {});

    render(
      <MemoryRouter initialEntries={['/events']}>
        <Routes>
          <Route
            path="/"
            element={
              <DashboardShell
                user={createUser()}
                onUserChange={vi.fn()}
                onRefreshProfile={onRefreshProfile}
              />
            }
          >
            <Route index element={<div>Dashboard Content</div>} />
            <Route path="events" element={<div>Events</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(authApi.getGuilds).toHaveBeenCalled();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Switch workspace' }));
    fireEvent.click(screen.getByRole('menuitemradio', { name: 'RSI Ops' }));

    await waitFor(() => {
      expect(authApi.selectGuild).toHaveBeenCalledWith('456');
    });
    expect(onRefreshProfile).toHaveBeenCalled();
  });

  it('shows logout only after opening the user menu', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route
            path="/"
            element={
              <DashboardShell
                user={createUser()}
                onUserChange={vi.fn()}
                onRefreshProfile={vi.fn(async () => {})}
              />
            }
          >
            <Route index element={<div>Dashboard Content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(authApi.getGuilds).toHaveBeenCalled();
    });

    expect(screen.queryByRole('menuitem', { name: 'Sign out' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Open user menu' }));

    expect(screen.getByRole('menu', { name: 'User options' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Sign out' })).toBeInTheDocument();
  });
});