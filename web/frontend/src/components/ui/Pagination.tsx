import { Button } from './Button';

export interface PaginationProps {
  page: number;
  totalPages: number;
  onPrevious: () => void;
  onNext: () => void;
  /** Optional left-side summary text, e.g. "Showing 1 to 25 of 100 results". */
  summary?: string;
  disabled?: boolean;
}

/**
 * Shared pagination controls — Previous / Page X of Y / Next.
 *
 * Used by Users table and Voice search results.
 */
export function Pagination({
  page,
  totalPages,
  onPrevious,
  onNext,
  summary,
  disabled = false,
}: PaginationProps) {
  const display = totalPages > 0 ? totalPages : 1;

  return (
    <div className="flex items-center justify-between">
      {summary && <div className="text-sm text-gray-400">{summary}</div>}
      <div className={`flex gap-2 ${summary ? '' : 'ml-auto'}`}>
        <Button
          variant="secondary"
          onClick={onPrevious}
          disabled={page === 1 || disabled}
        >
          Previous
        </Button>
        <div className="px-4 py-2 bg-slate-700 rounded">
          Page {page} of {display}
        </div>
        <Button
          variant="secondary"
          onClick={onNext}
          disabled={page >= totalPages || disabled}
        >
          Next
        </Button>
      </div>
    </div>
  );
}
