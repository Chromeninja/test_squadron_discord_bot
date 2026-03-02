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
                    <td className="px-3 py-2 font-mono text-xs text-gray-300">
                      {t.user_id}
                    </td>
                    <td className="px-3 py-2">
                      {getCategoryName(t.category_id, categories)}
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
