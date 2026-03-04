import React from 'react';
import { cn } from '../../utils/cn';

export interface PageHeaderProps {
  /** Page title */
  title: string;
  /** Optional subtitle / description */
  subtitle?: string;
  /** Right-side actions — stacked on mobile, inline on desktop */
  actions?: React.ReactNode;
  /** Additional className for the wrapper */
  className?: string;
}

/**
 * Consistent page header with title + optional actions area.
 *
 * Layout:
 * - Desktop: title left, actions right (flex row).
 * - Mobile: title full-width on top, actions below (flex col).
 * - 44 px minimum touch targets enforced in caller action buttons.
 */
export function PageHeader({ title, subtitle, actions, className }: PageHeaderProps) {
  return (
    <div
      className={cn(
        'flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between mb-4 lg:mb-6',
        className,
      )}
    >
      <div className="min-w-0">
        <h2 className="text-xl lg:text-2xl font-bold truncate">{title}</h2>
        {subtitle && (
          <p className="text-sm text-gray-400 mt-0.5 line-clamp-2">{subtitle}</p>
        )}
      </div>

      {actions && (
        <div className="flex flex-wrap gap-2 sm:flex-nowrap sm:shrink-0">{actions}</div>
      )}
    </div>
  );
}
