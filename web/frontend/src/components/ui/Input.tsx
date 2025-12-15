import React, { forwardRef } from 'react';
import { cn } from '../../utils/cn';
import { inputVariants } from '../../utils/theme';

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  /** Show error styling */
  error?: boolean;
  /** Optional label text */
  label?: string;
  /** Optional helper text below input */
  helperText?: string;
  /** Error message (also sets error=true) */
  errorMessage?: string;
  /** Full width input */
  fullWidth?: boolean;
  /** Optional left addon element */
  leftAddon?: React.ReactNode;
  /** Optional right addon element */
  rightAddon?: React.ReactNode;
}

/**
 * Text input component with consistent styling.
 * 
 * @example
 * // Basic input
 * <Input placeholder="Search..." value={query} onChange={handleChange} />
 * 
 * // With label and error
 * <Input 
 *   label="Email" 
 *   errorMessage="Invalid email format" 
 *   value={email}
 *   onChange={handleChange}
 * />
 * 
 * // With addons
 * <Input leftAddon={<SearchIcon />} placeholder="Search users..." />
 */
export const Input = forwardRef<HTMLInputElement, InputProps>(
  (
    {
      className,
      error,
      label,
      helperText,
      errorMessage,
      fullWidth = true,
      leftAddon,
      rightAddon,
      id,
      ...props
    },
    ref
  ) => {
    const inputId = id || label?.toLowerCase().replace(/\s+/g, '-');
    const hasError = error || !!errorMessage;

    const input = (
      <input
        ref={ref}
        id={inputId}
        className={cn(
          inputVariants.base,
          hasError && inputVariants.variant.error,
          leftAddon && 'pl-10',
          rightAddon && 'pr-10',
          !fullWidth && 'w-auto',
          className
        )}
        aria-invalid={hasError}
        aria-describedby={errorMessage ? `${inputId}-error` : helperText ? `${inputId}-helper` : undefined}
        {...props}
      />
    );

    // Simple input without wrapper
    if (!label && !helperText && !errorMessage && !leftAddon && !rightAddon) {
      return input;
    }

    return (
      <div className={cn('space-y-1', fullWidth && 'w-full')}>
        {label && (
          <label htmlFor={inputId} className="block text-sm font-medium text-gray-300">
            {label}
          </label>
        )}
        
        {(leftAddon || rightAddon) ? (
          <div className="relative">
            {leftAddon && (
              <div className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
                {leftAddon}
              </div>
            )}
            {input}
            {rightAddon && (
              <div className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400">
                {rightAddon}
              </div>
            )}
          </div>
        ) : input}

        {errorMessage && (
          <p id={`${inputId}-error`} className="text-sm text-red-400">
            {errorMessage}
          </p>
        )}
        
        {helperText && !errorMessage && (
          <p id={`${inputId}-helper`} className="text-sm text-gray-500">
            {helperText}
          </p>
        )}
      </div>
    );
  }
);

Input.displayName = 'Input';

// ============================================================================
// Textarea variant
// ============================================================================

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  /** Show error styling */
  error?: boolean;
  /** Optional label text */
  label?: string;
  /** Error message */
  errorMessage?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, error, label, errorMessage, id, ...props }, ref) => {
    const inputId = id || label?.toLowerCase().replace(/\s+/g, '-');
    const hasError = error || !!errorMessage;

    return (
      <div className="space-y-1 w-full">
        {label && (
          <label htmlFor={inputId} className="block text-sm font-medium text-gray-300">
            {label}
          </label>
        )}
        <textarea
          ref={ref}
          id={inputId}
          className={cn(
            inputVariants.base,
            hasError && inputVariants.variant.error,
            'min-h-[80px] resize-y',
            className
          )}
          aria-invalid={hasError}
          {...props}
        />
        {errorMessage && (
          <p className="text-sm text-red-400">{errorMessage}</p>
        )}
      </div>
    );
  }
);

Textarea.displayName = 'Textarea';
