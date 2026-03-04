import { useCallback } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { cn } from '../../utils/cn';

export interface MobileNavItem {
  to: string;
  label: string;
  icon: React.ReactNode;
  visible: boolean;
}

export interface MobileNavProps {
  items: MobileNavItem[];
}

/**
 * Bottom navigation bar for mobile screens (< 640 px).
 *
 * Design rules:
 * - Fixed to viewport bottom for thumb-zone access.
 * - Max 5 visible items to stay within 360 px width.
 * - 44 px minimum touch target per WCAG / Apple HIG.
 * - Active state uses org yellow accent.
 * - Hidden on desktop (lg+) via Tailwind responsive class.
 *
 * AI Notes:
 * Deliberately separate from header tabs so desktop keeps the horizontal
 * tab strip while mobile gets a bottom nav. The `items` array is filtered
 * by permission in the parent shell, not in this component.
 */
export function MobileNav({ items }: MobileNavProps) {
  const location = useLocation();

  const visibleItems = items.filter((i) => i.visible);

  const isActive = useCallback(
    (to: string) => {
      if (to === '/') return location.pathname === '/';
      return location.pathname.startsWith(to);
    },
    [location.pathname],
  );

  return (
    <nav
      className="lg:hidden fixed bottom-0 inset-x-0 z-40 bg-slate-900/95 border-t border-slate-700 dashboard-divider safe-area-bottom backdrop-blur-sm"
      role="navigation"
      aria-label="Main"
    >
      <ul className="flex justify-around items-center h-14">
        {visibleItems.map((item) => (
          <li key={item.to} className="flex-1 flex justify-center">
            <NavLink
              to={item.to}
              className={cn(
                'flex flex-col items-center justify-center gap-0.5 w-full min-h-[44px] text-[10px] font-medium transition-colors',
                isActive(item.to)
                  ? 'dashboard-nav-active'
                  : 'text-gray-400 active:text-yellow-200',
              )}
            >
              <span className="text-lg leading-none">{item.icon}</span>
              <span className="truncate max-w-[56px]">{item.label}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
