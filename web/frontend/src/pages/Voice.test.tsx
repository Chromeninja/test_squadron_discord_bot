import '@testing-library/jest-dom';
import { render, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const { mockedVoiceApi, useAuth } = vi.hoisted(() => ({
  mockedVoiceApi: {
    getIntegrity: vi.fn(),
    getActive: vi.fn(),
  },
  useAuth: vi.fn(),
}));

// Mock the API module
vi.mock('../api/endpoints', () => ({
  voiceApi: mockedVoiceApi,
  ALL_GUILDS_SENTINEL: '*',
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth,
}));

// Import after mocking
import { voiceApi } from '../api/endpoints';
import Voice from './Voice';

// Helper to create mock user profile
function createMockUserProfile(overrides = {}) {
  return {
    user_id: '123456789',
    username: 'TestUser',
    discriminator: '0',
    avatar: null,
    active_guild_id: '987654321',
    authorized_guilds: {
      '987654321': {
        guild_id: '987654321',
        role_level: 'bot_admin' as const,
        source: 'test',
      },
    },
    ...overrides,
  };
}

describe('Voice Page Rendering', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue({
      user: createMockUserProfile(),
      activeGuildId: '987654321',
      loading: false,
    });

    vi.mocked(voiceApi.getIntegrity).mockResolvedValue({
      count: 0,
      details: [],
    });
    
    vi.mocked(voiceApi.getActive).mockResolvedValue({
      success: true,
      items: [],
      total: 0,
    });
  });

  it('renders the voice page without crashing', async () => {
    render(<Voice />);
    
    // Should render the page with search functionality
    await waitFor(() => {
      // The page renders with some content
      expect(document.body.textContent).toBeTruthy();
    });
  });

  it('calls API endpoints on mount', async () => {
    render(<Voice />);

    await waitFor(() => {
      expect(voiceApi.getActive).toHaveBeenCalled();
      expect(voiceApi.getIntegrity).toHaveBeenCalled();
    });
  });

  it('handles API errors gracefully', async () => {
    vi.mocked(voiceApi.getActive).mockRejectedValue(new Error('API Error'));

    render(<Voice />);

    await waitFor(() => {
      expect(voiceApi.getActive).toHaveBeenCalled();
    });
  });
});

describe('Voice Page Permission Checks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue({
      user: createMockUserProfile(),
      activeGuildId: '987654321',
      loading: false,
    });

    vi.mocked(voiceApi.getIntegrity).mockResolvedValue({
      count: 0,
      details: [],
    });
    
    vi.mocked(voiceApi.getActive).mockResolvedValue({
      success: true,
      items: [],
      total: 0,
    });
  });

  it('renders for staff users', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: createMockUserProfile({
        authorized_guilds: {
          '987654321': {
            guild_id: '987654321',
            role_level: 'staff' as const,
            source: 'test',
          },
        },
      }),
      activeGuildId: '987654321',
      loading: false,
    });

    render(<Voice />);

    await waitFor(() => {
      expect(voiceApi.getActive).toHaveBeenCalled();
    });
  });

  it('renders for moderator users', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: createMockUserProfile({
        authorized_guilds: {
          '987654321': {
            guild_id: '987654321',
            role_level: 'moderator' as const,
            source: 'test',
          },
        },
      }),
      activeGuildId: '987654321',
      loading: false,
    });

    render(<Voice />);

    await waitFor(() => {
      expect(voiceApi.getActive).toHaveBeenCalled();
    });
  });

  it('renders for bot_admin users', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: createMockUserProfile({
        authorized_guilds: {
          '987654321': {
            guild_id: '987654321',
            role_level: 'bot_admin' as const,
            source: 'test',
          },
        },
      }),
      activeGuildId: '987654321',
      loading: false,
    });

    render(<Voice />);

    await waitFor(() => {
      expect(voiceApi.getActive).toHaveBeenCalled();
    });
  });
});
