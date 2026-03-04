import { Button } from './Button';
import { useIsMobile } from '../../hooks/useMediaQuery';

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
 * Mobile (< 640 px):
 * - Summary text hidden to save space.
 * - Compact: shorter button labels, smaller page indicator.
 * - Full width to fill the available horizontal space.
 *
 * Desktop:
 * - Summary on the left, controls on the right.
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
  const isMobile = useIsMobile();

  return (
    <div className="flex flex-col sm:flex-row items-center justify-between gap-2">
      {/* Summary — hidden on mobile */}
      {summary && (
        <div className="hidden sm:block text-sm text-gray-400">{summary}</div>
      )}

      <div className={`flex gap-2 ${summary ? '' : 'ml-auto'} ${isMobile ? 'w-full' : ''}`}>
        <Button
          variant="secondary"
          size={isMobile ? 'sm' : 'md'}
          onClick={onPrevious}
          disabled={page === 1 || disabled}
          className={isMobile ? 'flex-1 min-h-[44px]' : ''}
        >
          {isMobile ? '‹ Prev' : 'Previous'}
        </Button>

        <div className="px-3 py-2 bg-slate-700 rounded text-sm whitespace-nowrap flex items-center justify-center min-w-[80px]">
          {page} / {display}
        </div>

        <Button
          variant="secondary"
          size={isMobile ? 'sm' : 'md'}
          onClick={onNext}
          disabled={page >= totalPages || disabled}
          className={isMobile ? 'flex-1 min-h-[44px]' : ''}
        >
          {isMobile ? 'Next ›' : 'Next'}
        </Button>
      </div>
    </div>
  );
}
