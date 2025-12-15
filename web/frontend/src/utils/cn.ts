import { clsx, type ClassValue } from 'clsx';

/**
 * Utility function for conditionally joining className strings.
 * 
 * Combines clsx for conditional classes with clean output.
 * 
 * @example
 * // Simple usage
 * cn('base-class', isActive && 'active', className)
 * 
 * // With objects
 * cn('button', { 'button-primary': isPrimary, 'button-disabled': disabled })
 * 
 * // With arrays
 * cn(['base', condition && 'conditional'], extraClasses)
 */
export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs);
}
