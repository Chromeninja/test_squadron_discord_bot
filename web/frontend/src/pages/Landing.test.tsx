import '@testing-library/jest-dom';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Landing from './Landing';

const { authApi, handleApiError } = vi.hoisted(() => ({
  authApi: {
    getBotInviteUrl: vi.fn(),
  },
  handleApiError: vi.fn(),
}));

vi.mock('../api/endpoints', () => ({
  authApi,
}));

vi.mock('../utils/toast', () => ({
  handleApiError,
}));

function buildUser(isBotOwner: boolean) {
  return {
    user_id: '42',
    username: 'Test User',
    discriminator: '0001',
    avatar: null,
    active_guild_id: '123',
    authorized_guilds: {
      '123': {
        guild_id: '123',
        role_level: 'bot_admin' as const,
        source: 'test',
      },
    },
    is_bot_owner: isBotOwner,
  };
}

describe('Landing', () => {
  let locationAssignSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.clearAllMocks();
    locationAssignSpy = vi.spyOn(window.location, 'assign').mockImplementation(() => {});
  });

  it('hides Add Bot buttons for logged out users', () => {
    render(<Landing loginHref="/auth/login?next=%2F" user={null} />);

    expect(screen.queryByRole('button', { name: 'Add Bot to Server' })).not.toBeInTheDocument();
    expect(screen.queryByText('Add Bot: Bot Admin Only')).not.toBeInTheDocument();
  });

  it('shows Add Bot buttons as locked for non-admin users', () => {
    render(<Landing loginHref="/auth/login?next=%2F" user={buildUser(false)} />);

    const addButtons = screen.getAllByRole('button', { name: 'Add Bot to Server' });
    expect(addButtons[0]).toBeDisabled();
    expect(addButtons[1]).toBeDisabled();

    expect(
      screen.getByText('Locked: only bot admins can add the bot to servers.')
    ).toBeInTheDocument();
  });

  it('enables Add Bot for bot admins and starts invite flow', async () => {
    authApi.getBotInviteUrl.mockResolvedValue({
      invite_url: 'https://discord.com/oauth2/authorize?client_id=test',
    });

    render(<Landing loginHref="/auth/login?next=%2F" user={buildUser(true)} />);

    const addButtons = screen.getAllByRole('button', { name: 'Add Bot to Server' });
    expect(addButtons[0]).toBeEnabled();
    expect(addButtons[1]).toBeEnabled();

    fireEvent.click(addButtons[0]);

    await waitFor(() => {
      expect(authApi.getBotInviteUrl).toHaveBeenCalledTimes(1);
    });
    expect(locationAssignSpy).toHaveBeenCalledWith(
      'https://discord.com/oauth2/authorize?client_id=test'
    );
    expect(handleApiError).not.toHaveBeenCalled();
  });

  it('shows dashboard primary CTA for authenticated users', () => {
    render(
      <Landing
        loginHref="/auth/login?next=%2F"
        user={buildUser(true)}
        dashboardHref="/dashboard/123"
      />
    );

    expect(screen.getAllByRole('link', { name: 'Open Dashboard' })[0]).toHaveAttribute(
      'href',
      '/dashboard/123'
    );
  });
});
