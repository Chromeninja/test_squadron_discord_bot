import { useEffect, useState } from 'react';

/**
 * Reactive media-query hook.
 *
 * Returns `true` when the viewport matches the given CSS media query.
 * Updates on window resize / orientation change via `matchMedia`.
 *
 * @example
 * const isMobile = useMediaQuery('(max-width: 639px)');
 * const isTablet = useMediaQuery('(min-width: 640px) and (max-width: 1023px)');
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    const mql = window.matchMedia(query);

    const handler = (e: MediaQueryListEvent) => {
      setMatches(e.matches);
    };

    // Set initial value (may differ from SSR default)
    setMatches(mql.matches);
    mql.addEventListener('change', handler);

    return () => mql.removeEventListener('change', handler);
  }, [query]);

  return matches;
}

/**
 * Preset breakpoint hooks matching Tailwind defaults.
 *
 * - `useIsMobile()`  → < 640px  (below `sm`)
 * - `useIsTablet()`  → 640-1023px  (`sm` to below `lg`)
 * - `useIsDesktop()` → ≥ 1024px  (`lg`+)
 */
export function useIsMobile(): boolean {
  return useMediaQuery('(max-width: 639px)');
}

export function useIsTablet(): boolean {
  return useMediaQuery('(min-width: 640px) and (max-width: 1023px)');
}

export function useIsDesktop(): boolean {
  return useMediaQuery('(min-width: 1024px)');
}
