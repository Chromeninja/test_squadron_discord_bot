import '@testing-library/jest-dom';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const { eventsApi, guildApi, useAuth } = vi.hoisted(() => ({
  eventsApi: {
    getScheduledEvents: vi.fn(),
    createScheduledEvent: vi.fn(),
    updateScheduledEvent: vi.fn(),
  },
  guildApi: {
    getGuildInfo: vi.fn(),
    getGuildConfig: vi.fn(),
    getDiscordChannels: vi.fn(),
  },
  useAuth: vi.fn(),
}));

vi.mock('../api/endpoints', () => ({
  eventsApi,
  guildApi,
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth,
}));

import EventEditor from './EventEditor';
import Events from './Events';

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

describe('EventEditor Page', () => {
  function renderWithRouter(initialEntry: string) {
    return render(
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/events" element={<Events guildId="123" />} />
          <Route path="/events/new" element={<EventEditor guildId="123" mode="create" />} />
          <Route path="/events/:eventId/edit" element={<EventEditor guildId="123" mode="edit" />} />
        </Routes>
      </MemoryRouter>,
    );
  }

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue({
      user: createUser(),
      getUserRoleLevel: () => 'event_coordinator',
    });
    vi.mocked(guildApi.getGuildInfo).mockResolvedValue({
      success: true,
      guild: {
        guild_id: '123',
        guild_name: 'TEST Squadron',
        icon_url: null,
      },
    });
    vi.mocked(guildApi.getGuildConfig).mockResolvedValue({
      success: true,
      data: {
        roles: {
          bot_admins: [],
          discord_managers: [],
          moderators: [],
          event_coordinators: [],
          staff: [],
          bot_verified_role: [],
          main_role: [],
          affiliate_role: [],
          nonmember_role: [],
          delegation_policies: [],
        },
        channels: {
          verification_channel_id: null,
          bot_spam_channel_id: null,
          public_announcement_channel_id: null,
          leadership_announcement_channel_id: null,
        },
        voice: { selectable_roles: [] },
        metrics: { excluded_channel_ids: [] },
        organization: {
          organization_sid: null,
          organization_name: null,
          organization_logo_url: null,
        },
        events: {
          enabled: true,
          default_native_sync: true,
          default_announcement_channel_id: '10',
          default_voice_channel_id: '11',
        },
      },
    });
    vi.mocked(guildApi.getDiscordChannels).mockResolvedValue({
      success: true,
      channels: [
        { id: '10', name: 'events-feed', category: 'Ops', position: 1, type: 0 },
        { id: '11', name: 'Event Voice', category: 'Voice', position: 2, type: 2 },
      ],
    });
    vi.mocked(eventsApi.getScheduledEvents).mockResolvedValue({
      success: true,
      events: [
        {
          id: '555',
          name: 'Fleet Night',
          description: 'Weekly op',
          scheduled_start_time: '2026-04-09T20:00:00+00:00',
          scheduled_end_time: '2026-04-09T22:00:00+00:00',
          status: 'scheduled',
          entity_type: 'voice',
          channel_id: '11',
          channel_name: 'Event Voice',
          location: null,
          user_count: 12,
          creator_id: '444333222',
          creator_name: 'Coordinator',
          image_url: null,
        },
      ],
    });
    vi.mocked(eventsApi.createScheduledEvent).mockResolvedValue({
      success: true,
      event: {
        id: '777',
        name: 'Created Event',
        description: null,
        scheduled_start_time: '2026-04-10T20:00:00+00:00',
        scheduled_end_time: null,
        status: 'scheduled',
        entity_type: 'external',
        channel_id: null,
        channel_name: null,
        location: 'Spectrum',
        user_count: 0,
        creator_id: '444333222',
        creator_name: 'Coordinator',
        image_url: null,
      },
    });
    vi.mocked(eventsApi.updateScheduledEvent).mockResolvedValue({
      success: true,
      event: {
        id: '555',
        name: 'Fleet Night Updated',
        description: 'Updated weekly op',
        scheduled_start_time: '2026-04-09T21:00:00+00:00',
        scheduled_end_time: '2026-04-09T23:00:00+00:00',
        status: 'scheduled',
        entity_type: 'voice',
        channel_id: '11',
        channel_name: 'Event Voice',
        location: null,
        user_count: 12,
        creator_id: '444333222',
        creator_name: 'Coordinator',
        image_url: null,
      },
    });
  });

  it('creates an event through the full-page builder', async () => {
    renderWithRouter('/events/new');

    await waitFor(() => {
      expect(guildApi.getGuildInfo).toHaveBeenCalledWith('123');
    });

    fireEvent.change(screen.getByLabelText('Event Name'), {
      target: { value: 'Created Event' },
    });
    fireEvent.change(screen.getByLabelText('Start Date'), {
      target: { value: '2026-04-10' },
    });
    fireEvent.change(screen.getByLabelText('Start Time'), {
      target: { value: '20:00' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Publish Event' })).toBeEnabled();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Publish Event' }));

    await waitFor(() => {
      expect(eventsApi.createScheduledEvent).toHaveBeenCalledWith(
        '123',
        expect.objectContaining({ name: 'Created Event' }),
      );
    });

    await waitFor(() => {
      expect(screen.getByText('Upcoming and recent events')).toBeInTheDocument();
    });
  });

  it('edits an event through the full-page builder', async () => {
    renderWithRouter('/events/555/edit');

    await waitFor(() => {
      expect(eventsApi.getScheduledEvents).toHaveBeenCalledWith('123');
    });

    expect(screen.getByDisplayValue('Fleet Night')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Event Name'), {
      target: { value: 'Fleet Night Updated' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));

    await waitFor(() => {
      expect(eventsApi.updateScheduledEvent).toHaveBeenCalledWith(
        '123',
        '555',
        expect.objectContaining({ name: 'Fleet Night Updated' }),
      );
    });

    await waitFor(() => {
      expect(screen.getByText('Upcoming and recent events')).toBeInTheDocument();
    });
  });
});