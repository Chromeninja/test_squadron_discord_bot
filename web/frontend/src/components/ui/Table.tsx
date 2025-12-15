import React from 'react';
import { cn } from '../../utils/cn';
import { tableVariants } from '../../utils/theme';

// ============================================================================
// Table Components - Composable pattern
// ============================================================================

export interface TableProps extends React.TableHTMLAttributes<HTMLTableElement> {
  /** Wrap table in styled container */
  withWrapper?: boolean;
}

/**
 * Table component with consistent styling.
 * 
 * @example
 * <Table withWrapper>
 *   <TableHead>
 *     <TableRow>
 *       <TableHeader>Name</TableHeader>
 *       <TableHeader>Status</TableHeader>
 *     </TableRow>
 *   </TableHead>
 *   <TableBody>
 *     {items.map(item => (
 *       <TableRow key={item.id}>
 *         <TableCell>{item.name}</TableCell>
 *         <TableCell>{item.status}</TableCell>
 *       </TableRow>
 *     ))}
 *   </TableBody>
 * </Table>
 */
export function Table({ className, withWrapper = true, children, ...props }: TableProps) {
  const table = (
    <table className={cn(tableVariants.table, className)} {...props}>
      {children}
    </table>
  );

  if (withWrapper) {
    return <div className={tableVariants.wrapper}>{table}</div>;
  }

  return table;
}

export interface TableHeadProps extends React.HTMLAttributes<HTMLTableSectionElement> {}

export function TableHead({ className, children, ...props }: TableHeadProps) {
  return (
    <thead className={cn(tableVariants.thead, className)} {...props}>
      {children}
    </thead>
  );
}

export interface TableBodyProps extends React.HTMLAttributes<HTMLTableSectionElement> {}

export function TableBody({ className, children, ...props }: TableBodyProps) {
  return (
    <tbody className={cn(tableVariants.tbody, className)} {...props}>
      {children}
    </tbody>
  );
}

export interface TableRowProps extends React.HTMLAttributes<HTMLTableRowElement> {
  /** Disable hover effect */
  noHover?: boolean;
}

export function TableRow({ className, noHover = false, children, ...props }: TableRowProps) {
  return (
    <tr className={cn(!noHover && tableVariants.tr, className)} {...props}>
      {children}
    </tr>
  );
}

export interface TableHeaderProps extends React.ThHTMLAttributes<HTMLTableCellElement> {}

export function TableHeader({ className, children, ...props }: TableHeaderProps) {
  return (
    <th className={cn(tableVariants.th, className)} {...props}>
      {children}
    </th>
  );
}

export interface TableCellProps extends React.TdHTMLAttributes<HTMLTableCellElement> {}

export function TableCell({ className, children, ...props }: TableCellProps) {
  return (
    <td className={cn(tableVariants.td, className)} {...props}>
      {children}
    </td>
  );
}

// ============================================================================
// Empty State Component
// ============================================================================

export interface TableEmptyProps {
  /** Number of columns to span */
  colSpan: number;
  /** Message to display */
  message?: string;
  /** Optional icon */
  icon?: React.ReactNode;
}

/**
 * Empty state row for tables with no data.
 * 
 * @example
 * <TableBody>
 *   {items.length === 0 ? (
 *     <TableEmpty colSpan={3} message="No items found" />
 *   ) : (
 *     items.map(...)
 *   )}
 * </TableBody>
 */
export function TableEmpty({ colSpan, message = 'No data available', icon }: TableEmptyProps) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-4 py-8 text-center text-gray-500">
        <div className="flex flex-col items-center gap-2">
          {icon}
          <span className="text-sm italic">{message}</span>
        </div>
      </td>
    </tr>
  );
}

// ============================================================================
// Simple Data Table - Higher-level abstraction
// ============================================================================

export interface Column<T> {
  /** Column header text */
  header: string;
  /** Key to access data or render function */
  accessor: keyof T | ((row: T) => React.ReactNode);
  /** Optional header className */
  headerClassName?: string;
  /** Optional cell className */
  cellClassName?: string;
}

export interface DataTableProps<T> {
  /** Column definitions */
  columns: Column<T>[];
  /** Data rows */
  data: T[];
  /** Key extractor function */
  keyExtractor: (row: T) => string | number;
  /** Empty state message */
  emptyMessage?: string;
  /** Additional className for wrapper */
  className?: string;
}

/**
 * Higher-level data table with column definitions.
 * 
 * @example
 * const columns = [
 *   { header: 'Name', accessor: 'name' },
 *   { header: 'Status', accessor: (row) => <Badge>{row.status}</Badge> },
 * ];
 * 
 * <DataTable 
 *   columns={columns} 
 *   data={users}
 *   keyExtractor={(row) => row.id}
 * />
 */
export function DataTable<T>({
  columns,
  data,
  keyExtractor,
  emptyMessage = 'No data available',
  className,
}: DataTableProps<T>) {
  const renderCell = (row: T, column: Column<T>) => {
    if (typeof column.accessor === 'function') {
      return column.accessor(row);
    }
    const value = row[column.accessor];
    return value as React.ReactNode;
  };

  return (
    <Table className={className}>
      <TableHead>
        <TableRow noHover>
          {columns.map((column, idx) => (
            <TableHeader key={idx} className={column.headerClassName}>
              {column.header}
            </TableHeader>
          ))}
        </TableRow>
      </TableHead>
      <TableBody>
        {data.length === 0 ? (
          <TableEmpty colSpan={columns.length} message={emptyMessage} />
        ) : (
          data.map((row) => (
            <TableRow key={keyExtractor(row)}>
              {columns.map((column, idx) => (
                <TableCell key={idx} className={column.cellClassName}>
                  {renderCell(row, column)}
                </TableCell>
              ))}
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  );
}
