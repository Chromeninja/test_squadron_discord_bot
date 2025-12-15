import React from 'react';
import { cn } from '../../utils/cn';
import { badgeVariants, type BadgeVariant } from '../../utils/theme';

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  /** Visual style variant */
  variant?: BadgeVariant;
  /** Optional icon to display before text */
  icon?: React.ReactNode;
}

/**
 * Badge component for status indicators, labels, and tags.
 * 
 * @example
 * // Success badge
 * <Badge variant="success">Active</Badge>
 * 
 * // Warning badge with outline style
 * <Badge variant="warning-outline">Pending</Badge>
 * 
 * // With icon
 * <Badge variant="info" icon={<InfoIcon />}>New</Badge>
 */
export function Badge({
  className,
  variant = 'neutral',
  icon,
  children,
  ...props
}: BadgeProps) {
  return (
    <span
      className={cn(
        badgeVariants.base,
        badgeVariants.variant[variant],
        className
      )}
      {...props}
    >
      {icon && <span className="mr-1">{icon}</span>}
      {children}
    </span>
  );
}

// ============================================================================
// Pre-configured Badge Components for common use cases
// ============================================================================

export interface StatusBadgeProps {
  /** Boolean status to display */
  status: boolean;
  /** Label when status is true */
  trueLabel: string;
  /** Label when status is false */
  falseLabel: string;
  /** Optional className override */
  className?: string;
}

/**
 * Binary status badge that toggles between success/neutral based on boolean.
 * 
 * @example
 * <StatusBadge status={isLocked} trueLabel="Locked" falseLabel="Unlocked" />
 */
export function StatusBadge({ status, trueLabel, falseLabel, className }: StatusBadgeProps) {
  return (
    <Badge variant={status ? 'success' : 'neutral'} className={className}>
      {status ? trueLabel : falseLabel}
    </Badge>
  );
}

export interface MembershipBadgeProps {
  /** Membership status value */
  status: string | null | undefined;
  /** Optional className override */
  className?: string;
}

/**
 * Membership status badge with predefined color mappings.
 * 
 * @example
 * <MembershipBadge status="main" />
 * <MembershipBadge status="affiliate" />
 * <MembershipBadge status={null} /> // Shows "Not Verified"
 */
export function MembershipBadge({ status, className }: MembershipBadgeProps) {
  const variantMap: Record<string, BadgeVariant> = {
    main: 'success',
    affiliate: 'info',
    non_member: 'neutral',
  };

  const labelMap: Record<string, string> = {
    main: 'Main',
    affiliate: 'Affiliate',
    non_member: 'Not Member',
  };

  if (!status) {
    return (
      <Badge variant="neutral" className={cn('bg-gray-800 text-gray-500', className)}>
        Not Verified
      </Badge>
    );
  }

  const variant = variantMap[status] || 'neutral';
  const label = labelMap[status] || 'Unknown';

  return (
    <Badge variant={variant} className={className}>
      {label}
    </Badge>
  );
}
