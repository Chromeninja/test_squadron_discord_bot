import '@testing-library/jest-dom';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const { eventsApi, guildApi, useAuth } = vi.hoisted(() => ({
  eventsApi: {
    getScheduledEvents: vi.fn(),
    getScheduledEvent: vi.fn(),
    createScheduledEvent: vi.fn(),
    updateScheduledEvent: vi.fn(),
    deleteScheduledEvent: vi.fn(),
  },
  guildApi: {
    getGuildInfo: vi.fn(),
    getGuildConfig: vi.fn(),
    getDiscordChannels: vi.fn(),
    getDiscordRoles: vi.fn(),
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
        { id: '12', name: 'Town Hall', category: 'Ops', position: 3, type: 13 },
      ],
    });
    vi.mocked(guildApi.getDiscordRoles).mockResolvedValue({
      success: true,
      roles: [
        { id: '20', name: 'Pilot', color: null },
        { id: '21', name: 'Medic', color: null },
      ],
    });
    vi.mocked(eventsApi.getScheduledEvents).mockResolvedValue({
      success: true,
      events: [
        {
          id: '555',
          name: 'Fleet Night',
          description: 'Weekly op',
          scheduled_start_time: '2099-04-09T20:00:00+00:00',
          scheduled_end_time: '2099-04-09T22:00:00+00:00',
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
    vi.mocked(eventsApi.getScheduledEvent).mockResolvedValue({
      success: true,
      event: {
        id: '555',
        name: 'Fleet Night',
        description: 'Weekly op',
        scheduled_start_time: '2099-04-09T20:00:00+00:00',
        scheduled_end_time: '2099-04-09T22:00:00+00:00',
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
    vi.mocked(eventsApi.createScheduledEvent).mockResolvedValue({
      success: true,
      event: {
        id: '777',
        name: 'Created Event',
        description: null,
        scheduled_start_time: '2099-04-10T20:00:00+00:00',
        scheduled_end_time: null,
        status: 'scheduled',
        entity_type: 'voice',
        channel_id: '11',
        channel_name: 'Event Voice',
        location: null,
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
        scheduled_start_time: '2099-04-09T21:00:00+00:00',
        scheduled_end_time: '2099-04-09T23:00:00+00:00',
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
    vi.mocked(eventsApi.deleteScheduledEvent).mockResolvedValue({
      success: true,
    });
  });

  it('creates an event through the full-page builder', async () => {
    renderWithRouter('/events/new');

    await waitFor(() => {
      expect(guildApi.getGuildInfo).toHaveBeenCalledWith('123');
    });

    expect(screen.getByText('Where is your event?')).toBeInTheDocument();
    expect(screen.queryByText('Build flow')).not.toBeInTheDocument();
    expect(screen.queryByText('Live preview')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));

    fireEvent.change(screen.getByLabelText('Event Topic'), {
      target: { value: 'Created Event' },
    });
    fireEvent.change(screen.getByLabelText('Start Date'), {
      target: { value: '2026-04-10' },
    });
    fireEvent.change(screen.getByLabelText('Start Time'), {
      target: { value: '20:00' },
    });
    fireEvent.change(screen.getByLabelText('Description'), {
      target: { value: 'test event' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Create Event' })).toBeEnabled();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Create Event' }));

    await waitFor(() => {
      expect(eventsApi.createScheduledEvent).toHaveBeenCalledWith(
        '123',
        expect.objectContaining({
          name: 'Created Event',
          entity_type: 'voice',
          channel_id: '11',
          location: null,
          announcement_channel_id: '10',
          announcement_message: 'test event',
          signup_role_ids: [],
        }),
      );
    });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Delete Fleet Night' })).toBeInTheDocument();
    });
  });

  it('submits selected cover image data when creating an event', async () => {
    renderWithRouter('/events/new');

    await waitFor(() => {
      expect(guildApi.getGuildInfo).toHaveBeenCalledWith('123');
    });

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));

    fireEvent.change(screen.getByLabelText('Event Topic'), {
      target: { value: 'Image Event' },
    });
    fireEvent.change(screen.getByLabelText('Start Date'), {
      target: { value: '2026-04-10' },
    });
    fireEvent.change(screen.getByLabelText('Start Time'), {
      target: { value: '20:00' },
    });

    const imageFile = new File(['event-cover'], 'event-cover.png', { type: 'image/png' });
    fireEvent.change(screen.getByLabelText('Cover Image'), {
      target: { files: [imageFile] },
    });

    await waitFor(() => {
      expect(screen.getByRole('img', { name: 'Event cover preview' })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    fireEvent.click(screen.getByRole('button', { name: 'Create Event' }));

    await waitFor(() => {
      expect(eventsApi.createScheduledEvent).toHaveBeenCalledWith(
        '123',
        expect.objectContaining({
          name: 'Image Event',
          image_data: expect.stringMatching(/^data:image\/png;base64,/),
        }),
      );
    });
  });

  it('creates an external event with a location instead of a channel', async () => {
    renderWithRouter('/events/new');

    await waitFor(() => {
      expect(guildApi.getGuildInfo).toHaveBeenCalledWith('123');
    });

    fireEvent.click(screen.getByRole('button', { name: /Somewhere Else/ }));
    fireEvent.change(screen.getByLabelText('Enter a location'), {
      target: { value: 'Area 18 expo hall' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));

    fireEvent.change(screen.getByLabelText('Event Topic'), {
      target: { value: 'External Briefing' },
    });
    fireEvent.change(screen.getByLabelText('Start Date'), {
      target: { value: '2026-04-10' },
    });
    fireEvent.change(screen.getByLabelText('Start Time'), {
      target: { value: '20:00' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    fireEvent.click(screen.getByRole('button', { name: 'Create Event' }));

    await waitFor(() => {
      expect(eventsApi.createScheduledEvent).toHaveBeenCalledWith(
        '123',
        expect.objectContaining({
          name: 'External Briefing',
          entity_type: 'external',
          channel_id: null,
          location: 'Area 18 expo hall',
        }),
      );
    });
  });

  it('edits an event through the full-page builder', async () => {
    renderWithRouter('/events/555/edit');

    await waitFor(() => {
      expect(eventsApi.getScheduledEvent).toHaveBeenCalledWith('123', '555');
    });

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));

    expect(screen.getByDisplayValue('Fleet Night')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Event Topic'), {
      target: { value: 'Fleet Night Updated' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));

    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));

    await waitFor(() => {
      expect(eventsApi.updateScheduledEvent).toHaveBeenCalledWith(
        '123',
        '555',
        expect.objectContaining({ name: 'Fleet Night Updated' }),
      );
    });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Delete Fleet Night' })).toBeInTheDocument();
    });
  });

  it('previews existing Discord cover image without resubmitting image data', async () => {
    vi.mocked(eventsApi.getScheduledEvent).mockResolvedValue({
      success: true,
      event: {
        id: '555',
        name: 'Fleet Night',
        description: 'Weekly op',
        scheduled_start_time: '2099-04-09T20:00:00+00:00',
        scheduled_end_time: '2099-04-09T22:00:00+00:00',
        status: 'scheduled',
        entity_type: 'voice',
        channel_id: '11',
        channel_name: 'Event Voice',
        location: null,
        user_count: 12,
        creator_id: '444333222',
        creator_name: 'Coordinator',
        image_url: 'https://cdn.discordapp.com/guild-events/555/hash.png?size=1024',
      },
    });

    renderWithRouter('/events/555/edit');

    await waitFor(() => {
      expect(eventsApi.getScheduledEvent).toHaveBeenCalledWith('123', '555');
    });

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));

    await waitFor(() => {
      expect(screen.getByRole('img', { name: 'Event cover preview' })).toHaveAttribute(
        'src',
        'https://cdn.discordapp.com/guild-events/555/hash.png?size=1024',
      );
    });

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));

    await waitFor(() => {
      expect(eventsApi.updateScheduledEvent).toHaveBeenCalledWith(
        '123',
        '555',
        expect.objectContaining({ image_data: null }),
      );
    });
  });

  it('allows customizing the announcement message before publish', async () => {
    renderWithRouter('/events/new');

    await waitFor(() => {
      expect(guildApi.getGuildInfo).toHaveBeenCalledWith('123');
    });

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));

    fireEvent.change(screen.getByLabelText('Event Topic'), {
      target: { value: 'Apollo TEST' },
    });
    fireEvent.change(screen.getByLabelText('Description'), {
      target: { value: 'test brief' },
    });
    fireEvent.change(screen.getByLabelText('Start Date'), {
      target: { value: '2026-04-16' },
    });
    fireEvent.change(screen.getByLabelText('Start Time'), {
      target: { value: '16:00' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));

    fireEvent.change(screen.getByLabelText('Announcement Message'), {
      target: { value: 'Custom channel briefing for this op.' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    fireEvent.click(screen.getByRole('button', { name: 'Create Event' }));

    await waitFor(() => {
      expect(eventsApi.createScheduledEvent).toHaveBeenCalledWith(
        '123',
        expect.objectContaining({
          name: 'Apollo TEST',
          announcement_message: 'Custom channel briefing for this op.',
        }),
      );
    });
  });

  it('submits recurrence rule for weekly recurring events', async () => {
    renderWithRouter('/events/new');

    await waitFor(() => {
      expect(guildApi.getGuildInfo).toHaveBeenCalledWith('123');
    });

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));

    fireEvent.change(screen.getByLabelText('Event Topic'), {
      target: { value: 'Recurring Ops' },
    });
    fireEvent.change(screen.getByLabelText('Start Date'), {
      target: { value: '2026-04-16' },
    });
    fireEvent.change(screen.getByLabelText('Start Time'), {
      target: { value: '16:00' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Does not repeat' }));
    fireEvent.click(screen.getByRole('button', { name: 'Wed' }));

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    fireEvent.click(screen.getByRole('button', { name: 'Create Event' }));

    await waitFor(() => {
      expect(eventsApi.createScheduledEvent).toHaveBeenCalledWith(
        '123',
        expect.objectContaining({
          name: 'Recurring Ops',
          recurrence_rule: expect.objectContaining({
            frequency: 2,
            interval: 1,
            by_weekday: [2],
          }),
        }),
      );
    });
  });

  it('allows publishing without an announcement channel', async () => {
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
          default_announcement_channel_id: null,
          default_voice_channel_id: '11',
        },
      },
    });
    vi.mocked(guildApi.getDiscordChannels).mockResolvedValue({
      success: true,
      channels: [{ id: '11', name: 'Event Voice', category: 'Voice', position: 2, type: 2 }],
    });

    renderWithRouter('/events/new');

    await waitFor(() => {
      expect(guildApi.getGuildInfo).toHaveBeenCalledWith('123');
    });

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));

    fireEvent.change(screen.getByLabelText('Event Topic'), {
      target: { value: 'No Announcement Event' },
    });
    fireEvent.change(screen.getByLabelText('Start Date'), {
      target: { value: '2026-04-16' },
    });
    fireEvent.change(screen.getByLabelText('Start Time'), {
      target: { value: '16:00' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    fireEvent.click(screen.getByRole('button', { name: 'Create Event' }));

    await waitFor(() => {
      expect(eventsApi.createScheduledEvent).toHaveBeenCalledWith(
        '123',
        expect.objectContaining({
          name: 'No Announcement Event',
          announcement_channel_id: null,
        }),
      );
    });
  });

  it('confirms before deleting an event from the list', async () => {
    renderWithRouter('/events');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Delete Fleet Night' })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Delete Fleet Night' }));

    expect(screen.getByRole('heading', { name: 'Delete Event' })).toBeInTheDocument();
    expect(screen.getByText('Delete "Fleet Night"? This cannot be undone.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() => {
      expect(eventsApi.deleteScheduledEvent).toHaveBeenCalledWith('123', '555');
    });

    await waitFor(() => {
      expect(screen.queryByText('Fleet Night')).not.toBeInTheDocument();
    });
  });
});
