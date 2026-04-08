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
    bg: 'bg-[#3a2a00]',
    bgLight: 'bg-[#ffbb00]/12',
    text: 'text-[#ffe08a]',
    border: 'border-[#ffbb00]/30',
  },
  neutral: {
    bg: 'bg-[#17120a]',
    bgLight: 'bg-[#120d00]',
    text: 'text-[#d4c39b]',
    border: 'border-[#ffbb00]/15',
  },
  primary: {
    bg: 'bg-[#3a2a00]',
    bgLight: 'bg-[#ffbb00]/14',
    text: 'text-[#ffdd73]',
    border: 'border-[#ffbb00]/35',
  },
  purple: {
    bg: 'bg-[#241a00]',
    bgLight: 'bg-[#ffbb00]/10',
    text: 'text-[#ffe08a]',
    border: 'border-[#ffbb00]/28',
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
  base: 'inline-flex items-center justify-center font-medium rounded transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-black disabled:opacity-50 disabled:cursor-not-allowed',
  
  // Variant styles
  variant: {
    primary: 'border border-[#ffbb00]/45 bg-[linear-gradient(180deg,rgba(255,187,0,0.22),rgba(255,187,0,0.12))] text-[#fff1bf] focus:ring-[#ffbb00]/45 hover:bg-[linear-gradient(180deg,rgba(255,187,0,0.3),rgba(255,187,0,0.16))] disabled:bg-[#17120a] disabled:text-[#7d6c43]',
    secondary: 'border border-[#ffbb00]/18 bg-[#120d00] hover:bg-[#1a1304] text-[#f5deb3] focus:ring-[#ffbb00]/30 disabled:bg-black disabled:text-[#6e6143]',
    danger: 'bg-red-900/30 hover:bg-red-900/50 text-red-200 border border-red-700 focus:ring-red-500',
    warning: 'bg-yellow-900/30 hover:bg-yellow-900/50 text-yellow-200 border border-yellow-700 focus:ring-yellow-500',
    success: 'bg-green-900/30 hover:bg-green-900/50 text-green-200 border border-green-700 focus:ring-green-500',
    ghost: 'bg-transparent hover:bg-[#ffbb00]/8 text-[#d6c7a3] focus:ring-[#ffbb00]/30',
    link: 'bg-transparent text-[#ffcc4d] hover:text-[#fff1bf] underline-offset-4 hover:underline focus:ring-[#ffbb00]/45',
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
    info: 'bg-[#ffbb00]/12 text-[#ffe08a] border border-[#ffbb00]/25',
    neutral: 'bg-[#17120a] text-[#d4c39b] border border-[#ffbb00]/15',
    primary: 'bg-[#ffbb00]/14 text-[#ffdd73] border border-[#ffbb00]/30',
    purple: 'bg-[#241a00] text-[#ffe08a] border border-[#ffbb00]/25',
    orange: 'bg-orange-900 text-orange-200',
    // With border variants (for less prominent badges)
    'primary-outline': 'bg-[#ffbb00]/12 text-[#ffdd73] border border-[#ffbb00]/30',
    'warning-outline': 'bg-yellow-900/30 text-yellow-300 border border-yellow-700',
    'error-outline': 'bg-red-900/30 text-red-300 border border-red-700',
    'success-outline': 'bg-green-900/30 text-green-300 border border-green-700',
    'neutral-outline': 'bg-[#120d00] text-[#a89465] border border-[#ffbb00]/15',
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
    info: 'bg-[#ffbb00]/12 border-[#ffbb00]/28 text-[#ffe08a]',
    neutral: 'bg-[#120d00] border-[#ffbb00]/15 text-[#d4c39b]',
  },
} as const;

// ============================================================================
// Card Variants
// ============================================================================

export const cardVariants = {
  base: 'rounded-lg border shadow-[inset_0_1px_0_rgba(255,255,255,0.03),0_0_0_1px_rgba(255,187,0,0.04)]',
  
  variant: {
    default: 'bg-[linear-gradient(180deg,rgba(20,23,31,0.95),rgba(14,17,24,0.95))] border-[#ffbb00]/18 text-[#f5deb3]',
    dark: 'bg-[linear-gradient(180deg,rgba(12,14,18,0.96),rgba(8,9,12,0.96))] border-[#ffbb00]/14 text-[#f5deb3]',
    ghost: 'bg-[#120d00]/80 border-[#ffbb00]/14 text-[#d6c7a3]',
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
  base: 'w-full bg-[#120d00] border border-[#ffbb00]/18 rounded px-4 py-2 text-[#fff4cc] placeholder-[#7d6c43] focus:outline-none focus:border-[#ffbb00]/45 focus:ring-1 focus:ring-[#ffbb00]/35 disabled:bg-black disabled:text-[#6e6143] disabled:cursor-not-allowed',
  
  variant: {
    default: '',
    error: 'border-red-600 focus:border-red-500 focus:ring-red-500',
  },
} as const;

// ============================================================================
// Modal Variants
// ============================================================================

export const modalVariants = {
  overlay: 'fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4',
  container: 'bg-[linear-gradient(180deg,rgba(18,13,0,0.96),rgba(7,7,7,0.98))] rounded-lg border border-[#ffbb00]/18 w-full overflow-hidden text-[#f5deb3]',
  
  size: {
    sm: 'max-w-md',
    md: 'max-w-lg',
    lg: 'max-w-2xl',
    xl: 'max-w-4xl',
    full: 'max-w-full mx-4',
  },
  
  header: {
    base: 'px-6 py-4 border-b',
    default: 'border-[#ffbb00]/15 bg-[#120d00]',
    warning: 'bg-yellow-900/20 border-yellow-800',
    error: 'bg-red-900/20 border-red-800',
    success: 'bg-green-900/20 border-green-800',
    info: 'bg-[#ffbb00]/12 border-[#ffbb00]/30',
  },
} as const;

// ============================================================================
// Table Variants
// ============================================================================

export const tableVariants = {
  wrapper: 'bg-[#120d00]/80 rounded border border-[#ffbb00]/15 overflow-hidden',
  table: 'w-full text-sm',
  thead: 'bg-[#17120a] text-xs text-[#a89465]',
  th: 'text-left px-3 py-2 font-medium',
  tbody: 'divide-y divide-[#ffbb00]/12',
  tr: 'hover:bg-[#ffbb00]/6 transition-colors',
  td: 'px-3 py-2',
} as const;

// ============================================================================
// Membership Status Colors (domain-specific)
// ============================================================================

export const membershipStatusColors: Record<string, { bg: string; text: string }> = {
  main: { bg: 'bg-green-900', text: 'text-green-200' },
  affiliate: { bg: 'bg-[#3a2a00]', text: 'text-[#ffe08a]' },
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
