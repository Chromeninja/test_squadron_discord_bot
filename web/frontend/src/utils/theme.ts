/**
 * Centralized design tokens and theme utilities.
 * 
 * Single source of truth for colors, variants, and semantic styling.
 * All components should import from here rather than hardcoding Tailwind classes.
 */

// ============================================================================
// Color Palette - Semantic color mappings
// ============================================================================

export const colors = {
  // Status colors (background + text pairs)
  success: {
    bg: 'bg-green-900',
    bgLight: 'bg-green-900/20',
    text: 'text-green-200',
    border: 'border-green-800',
  },
  warning: {
    bg: 'bg-yellow-900',
    bgLight: 'bg-yellow-900/20',
    text: 'text-yellow-200',
    border: 'border-yellow-800',
  },
  error: {
    bg: 'bg-red-900',
    bgLight: 'bg-red-900/20',
    text: 'text-red-200',
    border: 'border-red-800',
  },
  info: {
    bg: 'bg-blue-900',
    bgLight: 'bg-blue-900/20',
    text: 'text-blue-200',
    border: 'border-blue-800',
  },
  neutral: {
    bg: 'bg-gray-700',
    bgLight: 'bg-gray-800',
    text: 'text-gray-300',
    border: 'border-gray-700',
  },
  primary: {
    bg: 'bg-indigo-900',
    bgLight: 'bg-indigo-900/30',
    text: 'text-indigo-200',
    border: 'border-indigo-700',
  },
  purple: {
    bg: 'bg-purple-900',
    bgLight: 'bg-purple-900/20',
    text: 'text-purple-200',
    border: 'border-purple-800',
  },
  orange: {
    bg: 'bg-orange-900',
    bgLight: 'bg-orange-900/20',
    text: 'text-orange-200',
    border: 'border-orange-800',
  },
} as const;

// ============================================================================
// Button Variants
// ============================================================================

export const buttonVariants = {
  // Base styles applied to all buttons
  base: 'inline-flex items-center justify-center font-medium rounded transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-slate-900 disabled:opacity-50 disabled:cursor-not-allowed',
  
  // Variant styles
  variant: {
    primary: 'bg-indigo-600 hover:bg-indigo-700 text-white focus:ring-indigo-500 disabled:bg-slate-600',
    secondary: 'bg-slate-700 hover:bg-slate-600 text-white focus:ring-slate-500 disabled:bg-slate-800 disabled:text-gray-600',
    danger: 'bg-red-900/30 hover:bg-red-900/50 text-red-200 border border-red-700 focus:ring-red-500',
    warning: 'bg-yellow-900/30 hover:bg-yellow-900/50 text-yellow-200 border border-yellow-700 focus:ring-yellow-500',
    success: 'bg-green-900/30 hover:bg-green-900/50 text-green-200 border border-green-700 focus:ring-green-500',
    ghost: 'bg-transparent hover:bg-slate-700 text-gray-300 focus:ring-slate-500',
    link: 'bg-transparent text-indigo-400 hover:text-indigo-300 underline-offset-4 hover:underline focus:ring-indigo-500',
  },
  
  // Size styles
  size: {
    sm: 'px-3 py-1.5 text-sm',
    md: 'px-4 py-2 text-sm',
    lg: 'px-6 py-2.5 text-base',
  },
} as const;

// ============================================================================
// Badge Variants
// ============================================================================

export const badgeVariants = {
  // Base styles
  base: 'inline-flex items-center px-2 py-0.5 text-xs font-semibold rounded',
  
  // Semantic variants
  variant: {
    success: 'bg-green-900 text-green-200',
    warning: 'bg-yellow-900 text-yellow-200',
    error: 'bg-red-900 text-red-200',
    info: 'bg-blue-900 text-blue-200',
    neutral: 'bg-gray-700 text-gray-300',
    primary: 'bg-indigo-900 text-indigo-200',
    purple: 'bg-purple-900 text-purple-200',
    orange: 'bg-orange-900 text-orange-200',
    // With border variants (for less prominent badges)
    'primary-outline': 'bg-indigo-900/50 text-indigo-200 border border-indigo-700',
    'warning-outline': 'bg-yellow-900/30 text-yellow-300 border border-yellow-700',
    'error-outline': 'bg-red-900/30 text-red-300 border border-red-700',
    'success-outline': 'bg-green-900/30 text-green-300 border border-green-700',
    'neutral-outline': 'bg-gray-800 text-gray-400 border border-gray-700',
  },
} as const;

// ============================================================================
// Alert Variants
// ============================================================================

export const alertVariants = {
  base: 'px-4 py-3 rounded-lg border',
  
  variant: {
    success: 'bg-green-900/20 border-green-800 text-green-200',
    warning: 'bg-yellow-900/20 border-yellow-800 text-yellow-200',
    error: 'bg-red-900/20 border-red-800 text-red-400',
    info: 'bg-blue-900/20 border-blue-800 text-blue-200',
    neutral: 'bg-slate-800 border-slate-700 text-gray-300',
  },
} as const;

// ============================================================================
// Card Variants
// ============================================================================

export const cardVariants = {
  base: 'rounded-lg border',
  
  variant: {
    default: 'bg-slate-800 border-slate-700',
    dark: 'bg-slate-900/50 border-slate-700',
    ghost: 'bg-slate-800/50 border-slate-700',
  },
  
  padding: {
    none: '',
    sm: 'p-3',
    md: 'p-4',
    lg: 'p-6',
  },
} as const;

// ============================================================================
// Input Variants
// ============================================================================

export const inputVariants = {
  base: 'w-full bg-slate-900 border border-slate-600 rounded px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 disabled:bg-slate-800 disabled:text-gray-500 disabled:cursor-not-allowed',
  
  variant: {
    default: '',
    error: 'border-red-600 focus:border-red-500 focus:ring-red-500',
  },
} as const;

// ============================================================================
// Modal Variants
// ============================================================================

export const modalVariants = {
  overlay: 'fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4',
  container: 'bg-slate-800 rounded-lg border border-slate-700 w-full overflow-hidden',
  
  size: {
    sm: 'max-w-md',
    md: 'max-w-lg',
    lg: 'max-w-2xl',
    xl: 'max-w-4xl',
    full: 'max-w-full mx-4',
  },
  
  header: {
    base: 'px-6 py-4 border-b',
    default: 'border-slate-700',
    warning: 'bg-yellow-900/20 border-yellow-800',
    error: 'bg-red-900/20 border-red-800',
    success: 'bg-green-900/20 border-green-800',
    info: 'bg-blue-900/20 border-blue-800',
  },
} as const;

// ============================================================================
// Table Variants
// ============================================================================

export const tableVariants = {
  wrapper: 'bg-slate-800/50 rounded border border-slate-700 overflow-hidden',
  table: 'w-full text-sm',
  thead: 'bg-slate-800/80 text-xs text-gray-400',
  th: 'text-left px-3 py-2 font-medium',
  tbody: 'divide-y divide-slate-700',
  tr: 'hover:bg-slate-700/30 transition-colors',
  td: 'px-3 py-2',
} as const;

// ============================================================================
// Membership Status Colors (domain-specific)
// ============================================================================

export const membershipStatusColors: Record<string, { bg: string; text: string }> = {
  main: { bg: 'bg-green-900', text: 'text-green-200' },
  affiliate: { bg: 'bg-blue-900', text: 'text-blue-200' },
  non_member: { bg: 'bg-gray-700', text: 'text-gray-300' },
  unknown: { bg: 'bg-gray-800', text: 'text-gray-400' },
  not_verified: { bg: 'bg-gray-800', text: 'text-gray-500' },
};

export const membershipStatusLabels: Record<string, string> = {
  main: 'Main',
  affiliate: 'Affiliate',
  non_member: 'Not Member',
  unknown: 'Unknown',
  not_verified: 'Not Verified',
};

// ============================================================================
// Type exports for component props
// ============================================================================

export type ButtonVariant = keyof typeof buttonVariants.variant;
export type ButtonSize = keyof typeof buttonVariants.size;
export type BadgeVariant = keyof typeof badgeVariants.variant;
export type AlertVariant = keyof typeof alertVariants.variant;
export type CardVariant = keyof typeof cardVariants.variant;
export type CardPadding = keyof typeof cardVariants.padding;
export type ModalSize = keyof typeof modalVariants.size;
export type ModalHeaderVariant = keyof typeof modalVariants.header;
