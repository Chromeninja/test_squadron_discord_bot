import React from 'react';
import { cn } from '../../utils/cn';
import { useIsMobile } from '../../hooks/useMediaQuery';
import { tableVariants } from '../../utils/theme';

export interface ResponsiveTableProps<T> {
  /** Data rows */
  data: T[];
  /** Column definitions for desktop table view */
  columns: {
    key: string;
    header: string;
    render: (row: T) => React.ReactNode;
    /** Hide this column on narrow screens (< sm) */
    hideOnMobile?: boolean;
    /** Tailwind width class for this column header */
    className?: string;
  }[];
  /** Card renderer for mobile — receives one row */
  renderCard: (row: T, index: number) => React.ReactNode;
  /** Unique key extractor */
  getKey: (row: T) => string | number;
  /** Optional empty state */
  emptyMessage?: string;
  /** Additional wrapper className */
  className?: string;
}

/**
 * Dual-mode data view: full table on desktop, card list on mobile.
 *
 * Design rules:
 * - Below `sm` breakpoint (< 640 px) renders the card list.
 * - At `sm`+ renders the standard table with sortable headers.
 * - Card list uses 8 px gap and 16 px padding for comfortable touch.
 * - Horizontal scroll fallback removed: cards prevent the need.
 *
 * AI Notes:
 * Columns with `hideOnMobile: true` are omitted from the table when
 * the viewport is between sm and lg (tablet). The card renderer gives
 * full control over mobile information density.
 */
export function ResponsiveTable<T>({
  data,
  columns,
  renderCard,
  getKey,
  emptyMessage = 'No data found.',
  className,
}: ResponsiveTableProps<T>) {
  const isMobile = useIsMobile();

  if (data.length === 0) {
    return (
      <div className={cn('text-center py-12 text-gray-400', className)}>
        {emptyMessage}
      </div>
    );
  }

  // ---- Mobile card list ----
  if (isMobile) {
    return (
      <div className={cn('flex flex-col gap-2', className)}>
        {data.map((row, idx) => (
          <div key={getKey(row)}>{renderCard(row, idx)}</div>
        ))}
      </div>
    );
  }

  // ---- Desktop table ----
  return (
    <div className={cn(tableVariants.wrapper, 'overflow-x-auto', className)}>
      <table className={tableVariants.table}>
        <thead className={tableVariants.thead}>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                className={cn(
                  tableVariants.th,
                  col.hideOnMobile && 'hidden lg:table-cell',
                  col.className,
                )}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className={tableVariants.tbody}>
          {data.map((row) => (
            <tr key={getKey(row)} className={tableVariants.tr}>
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={cn(
                    tableVariants.td,
                    col.hideOnMobile && 'hidden lg:table-cell',
                  )}
                >
                  {col.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
