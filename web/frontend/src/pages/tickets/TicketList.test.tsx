import '@testing-library/jest-dom';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import TicketList from './TicketList';

describe('TicketList', () => {
  it('renders resolved creator identity and thread link', () => {
    render(
      <TicketList
        tickets={[
          {
            id: 42,
            guild_id: '123456789',
            channel_id: '111111111',
            thread_id: '222222222',
            user_id: '999999999999',
            creator_username: 'PilotOne',
            creator_global_name: 'Admiral Pilot',
            creator_discriminator: '0001',
            category_id: 7,
            status: 'open',
            closed_by: null,
            created_at: 1710000000,
            closed_at: null,
          },
        ]}
        categories={[
          {
            id: 7,
            guild_id: '123456789',
            name: 'Support',
            description: 'Support queue',
            welcome_message: 'Welcome',
            role_ids: [],
            prerequisite_role_ids_all: [],
            prerequisite_role_ids_any: [],
            emoji: null,
            sort_order: 0,
            created_at: 1710000000,
            channel_id: '111111111',
          },
        ]}
        ticketFilter=""
        ticketPage={1}
        ticketTotal={1}
        onFilterChange={() => {}}
        onPageChange={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Tickets' }));

    expect(screen.getByText('Admiral Pilot')).toBeInTheDocument();
    expect(screen.getByText('PilotOne#0001')).toBeInTheDocument();
    expect(screen.getByText('999999999999')).toBeInTheDocument();

    const threadLink = screen.getByRole('link', { name: 'Open Thread' });
    expect(threadLink).toHaveAttribute(
      'href',
      'https://discord.com/channels/123456789/222222222',
    );
  });

  it('falls back to shortened user label when creator identity is unavailable', () => {
    render(
      <TicketList
        tickets={[
          {
            id: 7,
            guild_id: '333333333',
            channel_id: '444444444',
            thread_id: '555555555',
            user_id: '123456789012',
            category_id: null,
            status: 'closed',
            closed_by: null,
            created_at: 1710000000,
            closed_at: 1710003600,
          },
        ]}
        categories={[]}
        ticketFilter=""
        ticketPage={1}
        ticketTotal={1}
        onFilterChange={() => {}}
        onPageChange={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Tickets' }));

    expect(screen.getByText('User 789012')).toBeInTheDocument();
  });
});
