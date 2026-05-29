/** Paginated ticket list with status filter. */

import type { TicketCategory, TicketInfo } from '../../api/endpoints';
import AccordionSection from '../../components/AccordionSection';
import { Alert, Badge, Pagination } from '../../components/ui';
import { TICKET_PAGE_SIZE } from './constants';
import { formatTimestamp, getCategoryName } from './utils';

interface TicketListProps {
  tickets: TicketInfo[];
  categories: TicketCategory[];
  ticketFilter: string;
  ticketPage: number;
  ticketTotal: number;
  onFilterChange: (filter: string) => void;
  onPageChange: (page: number) => void;
}

function getCreatorLabel(ticket: TicketInfo): string {
  if (ticket.creator_global_name) {
    return ticket.creator_global_name;
  }
  if (ticket.creator_username) {
    return ticket.creator_username;
  }
  return `User ${ticket.user_id.slice(-6)}`;
}

function getCreatorTag(ticket: TicketInfo): string | null {
  if (!ticket.creator_username) {
    return null;
  }
  if (!ticket.creator_discriminator) {
    return ticket.creator_username;
  }
  return `${ticket.creator_username}#${ticket.creator_discriminator}`;
}

function getThreadUrl(ticket: TicketInfo): string {
  return `https://discord.com/channels/${ticket.guild_id}/${ticket.thread_id}`;
}

export default function TicketList({
  tickets,
  categories,
  ticketFilter,
  ticketPage,
  ticketTotal,
  onFilterChange,
  onPageChange,
}: TicketListProps) {
  const totalPages = Math.ceil(ticketTotal / TICKET_PAGE_SIZE) || 1;

  return (
    <AccordionSection title="Tickets">
      <div className="space-y-4">
        {/* Filter */}
        <div className="flex items-center gap-3">
          <label htmlFor="ticket-status-filter" className="text-sm text-gray-400">
            Filter:
          </label>
          <select
            id="ticket-status-filter"
            value={ticketFilter}
            onChange={(e) => {
              onFilterChange(e.target.value);
              onPageChange(1);
            }}
            className="bg-slate-900 border border-slate-600 rounded px-3 py-1.5 text-sm text-white focus:outline-none focus:border-indigo-500"
          >
            <option value="">All</option>
            <option value="open">Open</option>
            <option value="closed">Closed</option>
          </select>
        </div>

        {/* Table */}
        {tickets.length === 0 ? (
          <Alert variant="info">No tickets found.</Alert>
        ) : (
          <div className="bg-slate-800/50 rounded border border-slate-700 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-800/80 text-xs text-gray-400">
                <tr>
                  <th className="text-left px-3 py-2 font-medium">ID</th>
                  <th className="text-left px-3 py-2 font-medium">Creator</th>
                  <th className="text-left px-3 py-2 font-medium">Category</th>
                  <th className="text-left px-3 py-2 font-medium">Thread</th>
                  <th className="text-left px-3 py-2 font-medium">Status</th>
                  <th className="text-left px-3 py-2 font-medium">Created</th>
                  <th className="text-left px-3 py-2 font-medium">Closed</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {tickets.map((t) => (
                  <tr
                    key={t.id}
                    className="hover:bg-slate-700/30 transition-colors"
                  >
                    <td className="px-3 py-2 font-mono text-xs">{t.id}</td>
                    <td className="px-3 py-2 text-xs text-gray-300">
                      <div className="max-w-[220px] truncate font-medium text-gray-200">
                        {getCreatorLabel(t)}
                      </div>
                      {getCreatorTag(t) && (
                        <div className="max-w-[220px] truncate text-gray-400">
                          {getCreatorTag(t)}
                        </div>
                      )}
                      <div className="font-mono text-[11px] text-gray-500">{t.user_id}</div>
                    </td>
                    <td className="px-3 py-2">
                      {getCategoryName(t.category_id, categories)}
                    </td>
                    <td className="px-3 py-2 text-xs">
                      <a
                        href={getThreadUrl(t)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-indigo-300 hover:text-indigo-200 hover:underline"
                      >
                        Open Thread
                      </a>
                    </td>
                    <td className="px-3 py-2">
                      <Badge variant={t.status === 'open' ? 'success' : 'neutral'}>
                        {t.status}
                      </Badge>
                    </td>
                    <td className="px-3 py-2 text-xs text-gray-400">
                      {formatTimestamp(t.created_at)}
                    </td>
                    <td className="px-3 py-2 text-xs text-gray-400">
                      {formatTimestamp(t.closed_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {ticketTotal > TICKET_PAGE_SIZE && (
          <Pagination
            page={ticketPage}
            totalPages={totalPages}
            onPrevious={() => onPageChange(Math.max(1, ticketPage - 1))}
            onNext={() => onPageChange(Math.min(totalPages, ticketPage + 1))}
            summary={`${ticketTotal} ticket${ticketTotal !== 1 ? 's' : ''}`}
          />
        )}
      </div>
    </AccordionSection>
  );
}
