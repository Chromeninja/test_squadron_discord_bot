import React from 'react';
import { cn } from '../../utils/cn';
import { alertVariants, type AlertVariant } from '../../utils/theme';

export interface AlertProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Visual style variant */
  variant?: AlertVariant;
  /** Optional title */
  title?: string;
  /** Optional icon */
  icon?: React.ReactNode;
  /** Optional action element (button, link, etc.) */
  action?: React.ReactNode;
  /** Whether alert can be dismissed */
  dismissible?: boolean;
  /** Callback when dismissed */
  onDismiss?: () => void;
}

/**
 * Alert component for displaying feedback messages.
 * 
 * @example
 * // Error alert
 * <Alert variant="error">Failed to load data</Alert>
 * 
 * // Success with title and action
 * <Alert 
 *   variant="success" 
 *   title="Settings saved"
 *   action={<button>Undo</button>}
 * >
 *   Your changes have been applied.
 * </Alert>
 * 
 * // Dismissible warning
 * <Alert variant="warning" dismissible onDismiss={() => setShow(false)}>
 *   This action cannot be undone.
 * </Alert>
 */
export function Alert({
  className,
  variant = 'neutral',
  title,
  icon,
  action,
  dismissible = false,
  onDismiss,
  children,
  ...props
}: AlertProps) {
  return (
    <div
      role="alert"
      className={cn(
        alertVariants.base,
        alertVariants.variant[variant],
        'relative',
        className
      )}
      {...props}
    >
      <div className="flex items-start gap-3">
        {icon && <div className="flex-shrink-0 mt-0.5">{icon}</div>}
        
        <div className="flex-1 min-w-0">
          {title && <p className="font-semibold mb-1">{title}</p>}
          <div className="text-sm">{children}</div>
        </div>

        {action && <div className="flex-shrink-0">{action}</div>}

        {dismissible && (
          <button
            onClick={onDismiss}
            className="flex-shrink-0 p-1 hover:opacity-70 transition-opacity"
            aria-label="Dismiss"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// Banner variant (full-width, typically at top of page)
// ============================================================================

export interface BannerProps extends Omit<AlertProps, 'dismissible'> {
  /** Center content horizontally */
  centered?: boolean;
  /** Max width constraint */
  maxWidth?: 'sm' | 'md' | 'lg' | 'xl' | '2xl' | '4xl' | 'full';
}

/**
 * Banner component for page-level notifications.
 * 
 * @example
 * <Banner variant="warning" maxWidth="4xl" centered>
 *   <strong>5 corrupted entries detected.</strong>{' '}
 *   <button className="underline">View details</button>
 * </Banner>
 */
export function Banner({
  className,
  variant = 'warning',
  centered = true,
  maxWidth = '4xl',
  children,
  ...props
}: BannerProps) {
  const maxWidthClasses: Record<string, string> = {
    sm: 'max-w-sm',
    md: 'max-w-md',
    lg: 'max-w-lg',
    xl: 'max-w-xl',
    '2xl': 'max-w-2xl',
    '4xl': 'max-w-4xl',
    full: 'max-w-full',
  };

  return (
    <Alert
      variant={variant}
      className={cn(
        'mb-4',
        centered && 'mx-auto',
        maxWidthClasses[maxWidth],
        className
      )}
      {...props}
    >
      {children}
    </Alert>
  );
}
