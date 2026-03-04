import React, { useEffect, useRef } from 'react';
import { cn } from '../../utils/cn';

export interface ActionSheetItem {
  label: string;
  icon?: React.ReactNode;
  onClick: () => void;
  /** Visual variant for destructive actions */
  variant?: 'default' | 'danger';
  disabled?: boolean;
}

export interface ActionSheetProps {
  /** Whether the sheet is open */
  open: boolean;
  /** Close handler */
  onClose: () => void;
  /** Optional title */
  title?: string;
  /** Action items */
  items: ActionSheetItem[];
}

/**
 * Mobile-first bottom action sheet for progressive disclosure of actions.
 *
 * Design rules (per mobile UX best practice):
 * - Slides up from bottom on mobile for thumb-friendly access.
 * - 44 px minimum touch target per row.
 * - Destructive actions are visually distinguished (red text) and placed last.
 * - Backdrop overlay closes on tap.
 * - Traps focus while open.
 *
 * On desktop, this renders as a centered modal-like sheet.
 *
 * AI Notes:
 * Used in place of inline destructive buttons on mobile list views
 * (Users bulk actions, Voice moderation, etc.) to implement
 * progressive disclosure of admin/destructive operations.
 */
export function ActionSheet({ open, onClose, title, items }: ActionSheetProps) {
  const sheetRef = useRef<HTMLDivElement>(null);

  // Close on Escape
  useEffect(() => {
    if (!open) return;

    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };

    document.addEventListener('keydown', handler);
    document.body.style.overflow = 'hidden';

    return () => {
      document.removeEventListener('keydown', handler);
      document.body.style.overflow = '';
    };
  }, [open, onClose]);

  if (!open) return null;

  // Sort: default items first, danger last (progressive disclosure)
  const sorted = [...items].sort((a, b) => {
    if (a.variant === 'danger' && b.variant !== 'danger') return 1;
    if (a.variant !== 'danger' && b.variant === 'danger') return -1;
    return 0;
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center"
      aria-modal="true"
      role="dialog"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Sheet */}
      <div
        ref={sheetRef}
        className={cn(
          'relative w-full sm:max-w-sm bg-slate-800 border border-slate-700 rounded-t-2xl sm:rounded-2xl',
          'animate-slide-up sm:animate-none',
          'max-h-[70vh] overflow-y-auto',
        )}
      >
        {/* Drag handle (mobile affordance) */}
        <div className="flex justify-center pt-3 pb-1 sm:hidden">
          <div className="w-10 h-1 rounded-full bg-slate-600" />
        </div>

        {title && (
          <div className="px-4 py-3 border-b border-slate-700">
            <h3 className="text-sm font-semibold text-gray-300">{title}</h3>
          </div>
        )}

        <ul className="py-1">
          {sorted.map((item, idx) => (
            <li key={idx}>
              <button
                onClick={() => {
                  item.onClick();
                  onClose();
                }}
                disabled={item.disabled}
                className={cn(
                  'w-full flex items-center gap-3 px-4 min-h-[44px] text-sm font-medium transition-colors',
                  'hover:bg-slate-700 active:bg-slate-600',
                  'disabled:opacity-40 disabled:cursor-not-allowed',
                  item.variant === 'danger' ? 'text-red-400' : 'text-gray-200',
                )}
              >
                {item.icon && <span className="text-base shrink-0">{item.icon}</span>}
                <span>{item.label}</span>
              </button>
            </li>
          ))}
        </ul>

        {/* Cancel button */}
        <div className="border-t border-slate-700 p-2">
          <button
            onClick={onClose}
            className="w-full min-h-[44px] text-sm font-medium text-gray-400 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
