import React from 'react';
import { cn } from '../../utils/cn';
import { cardVariants, type CardVariant, type CardPadding } from '../../utils/theme';

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Visual style variant */
  variant?: CardVariant;
  /** Padding size */
  padding?: CardPadding;
  /** Make card hoverable with visual feedback */
  hoverable?: boolean;
}

/**
 * Card container component for grouping related content.
 * 
 * @example
 * // Default card with padding
 * <Card padding="md">
 *   <h3>Title</h3>
 *   <p>Content</p>
 * </Card>
 * 
 * // Dark variant without padding (for custom layouts)
 * <Card variant="dark" padding="none">
 *   <CardHeader>...</CardHeader>
 *   <CardBody>...</CardBody>
 * </Card>
 */
export function Card({
  className,
  variant = 'default',
  padding = 'md',
  hoverable = false,
  children,
  ...props
}: CardProps) {
  return (
    <div
      className={cn(
        cardVariants.base,
        cardVariants.variant[variant],
        cardVariants.padding[padding],
        hoverable && 'hover:bg-slate-700/50 transition-colors cursor-pointer',
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
}

// ============================================================================
// Card sub-components for structured layouts
// ============================================================================

export interface CardHeaderProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Title text */
  title?: string;
  /** Optional subtitle or description */
  subtitle?: string;
  /** Optional actions (buttons, etc.) to display on the right */
  actions?: React.ReactNode;
}

/**
 * Card header with optional title, subtitle, and actions.
 */
export function CardHeader({
  className,
  title,
  subtitle,
  actions,
  children,
  ...props
}: CardHeaderProps) {
  // If children are provided, render them directly
  if (children) {
    return (
      <div className={cn('px-6 py-4 border-b border-slate-700', className)} {...props}>
        {children}
      </div>
    );
  }

  return (
    <div
      className={cn('px-6 py-4 border-b border-slate-700 flex items-center justify-between', className)}
      {...props}
    >
      <div>
        {title && <h3 className="text-lg font-semibold">{title}</h3>}
        {subtitle && <p className="text-sm text-gray-400 mt-0.5">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export interface CardBodyProps extends React.HTMLAttributes<HTMLDivElement> {}

/**
 * Card body for main content area.
 */
export function CardBody({ className, children, ...props }: CardBodyProps) {
  return (
    <div className={cn('px-6 py-4', className)} {...props}>
      {children}
    </div>
  );
}

export interface CardFooterProps extends React.HTMLAttributes<HTMLDivElement> {}

/**
 * Card footer for actions or secondary information.
 */
export function CardFooter({ className, children, ...props }: CardFooterProps) {
  return (
    <div className={cn('px-6 py-4 border-t border-slate-700', className)} {...props}>
      {children}
    </div>
  );
}

// ============================================================================
// Collapsible Card variant
// ============================================================================

export interface CollapsibleCardProps extends Omit<CardProps, 'padding'> {
  /** Whether the card is expanded */
  expanded: boolean;
  /** Toggle function */
  onToggle: () => void;
  /** Header content (always visible) */
  header: React.ReactNode;
  /** Optional right-side content in header */
  headerRight?: React.ReactNode;
}

/**
 * Collapsible card with expandable content.
 * 
 * @example
 * <CollapsibleCard
 *   expanded={isExpanded}
 *   onToggle={() => setExpanded(!isExpanded)}
 *   header={<span>Channel Name</span>}
 *   headerRight={<span>3 members</span>}
 * >
 *   <MemberList members={members} />
 * </CollapsibleCard>
 */
export function CollapsibleCard({
  className,
  variant = 'default',
  expanded,
  onToggle,
  header,
  headerRight,
  children,
  ...props
}: CollapsibleCardProps) {
  return (
    <Card variant={variant} padding="none" className={cn('overflow-hidden', className)} {...props}>
      <button
        onClick={onToggle}
        className="w-full px-6 py-4 flex items-center justify-between hover:bg-slate-700/50 transition"
      >
        <div className="flex items-center gap-4">
          <ChevronIcon expanded={expanded} />
          <div className="text-left">{header}</div>
        </div>
        {headerRight && <div className="flex items-center gap-4">{headerRight}</div>}
      </button>

      {expanded && (
        <div className="px-6 py-4 bg-slate-900/50 border-t border-slate-700">
          {children}
        </div>
      )}
    </Card>
  );
}

/** Chevron icon that rotates based on expanded state */
function ChevronIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg
      className={cn('w-5 h-5 text-gray-400 transition-transform', expanded && 'rotate-90')}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
    >
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
    </svg>
  );
}
