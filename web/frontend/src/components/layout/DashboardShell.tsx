import { useCallback, useMemo, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { MobileNav, type MobileNavItem } from './MobileNav';
import { useIsMobile } from '../../hooks/useMediaQuery';
import { cn } from '../../utils/cn';
import { authApi, type UserProfile } from '../../api/endpoints';
import {
  hasPermission,
  getRoleBadgeColor,
  getRoleDisplayName,
  type RoleLevel,
} from '../../utils/permissions';
import { handleApiError } from '../../utils/toast';

export interface DashboardShellProps {
  user: UserProfile;
  onUserChange: (user: UserProfile | null) => void;
  onRefreshProfile: () => Promise<void>;
}

/**
 * Root layout shell rendered inside the router.
 *
 * Responsibilities:
 * - Desktop: top header + horizontal tab strip + <Outlet />
 * - Mobile (< 640 px): compact header + <Outlet /> + bottom nav bar
 * - Permission-gated tab/nav item visibility
 * - Server switch & logout actions
 *
 * AI Notes:
 * This component replaces the old inline layout in App.tsx.
 * It renders <Outlet /> for the active route's page component.
 * The bottom nav is only mounted on mobile to keep DOM lean.
 */
export function DashboardShell({ user, onUserChange, onRefreshProfile }: DashboardShellProps) {
  const isMobile = useIsMobile();
  const navigate = useNavigate();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // ---- Permission helpers ----
  const getUserRoleLevel = useCallback((): RoleLevel => {
    if (!user.active_guild_id) return 'user';
    const permission = user.authorized_guilds[user.active_guild_id];
    return permission?.role_level || 'user';
  }, [user]);

  const userHasPermission = useCallback(
    (required: RoleLevel): boolean => hasPermission(getUserRoleLevel(), required),
    [getUserRoleLevel],
  );

  const canViewMetrics = userHasPermission('discord_manager');

  // ---- Navigation items (shared between desktop tabs + mobile bottom nav) ----
  const navItems: MobileNavItem[] = useMemo(
    () => [
      { to: '/', label: 'Dashboard', icon: '📊', visible: true },
      { to: '/metrics', label: 'Metrics', icon: '📈', visible: canViewMetrics },
      { to: '/users', label: 'Users', icon: '👥', visible: true },
      { to: '/voice', label: 'Voice', icon: '🔊', visible: true },
      { to: '/tickets', label: 'Tickets', icon: '🎫', visible: userHasPermission('discord_manager') },
      { to: '/settings', label: 'Settings', icon: '⚙️', visible: userHasPermission('bot_admin') },
    ],
    [canViewMetrics, userHasPermission],
  );

  const visibleNavItems = useMemo(() => navItems.filter((i) => i.visible), [navItems]);

  // ---- Actions ----
  const handleSwitchServer = async () => {
    try {
      await authApi.clearActiveGuild();
      await onRefreshProfile();
    } catch (err) {
      handleApiError(err, 'Failed to switch server');
    }
  };

  const handleLogout = async () => {
    try {
      await authApi.logout();
      onUserChange(null);
      navigate('/');
      window.location.href = '/';
    } catch (err) {
      handleApiError(err, 'Failed to log out');
    }
  };

  // Role badge
  const roleBadge = (() => {
    if (user.active_guild_id && user.authorized_guilds?.[user.active_guild_id]) {
      const level = user.authorized_guilds[user.active_guild_id].role_level;
      return (
        <span className={cn('px-2 py-1 text-xs font-semibold rounded', getRoleBadgeColor(level))}>
          {getRoleDisplayName(level).toUpperCase()}
        </span>
      );
    }
    if (user.is_admin) {
      return <span className="px-2 py-1 text-xs font-semibold bg-red-900 text-red-200 rounded">ADMIN</span>;
    }
    if (user.is_moderator) {
      return <span className="px-2 py-1 text-xs font-semibold bg-blue-900 text-blue-200 rounded">MOD</span>;
    }
    return null;
  })();

  return (
    <div className="min-h-screen bg-slate-900 flex flex-col dashboard-theme">
      <Toaster />

      {/* ---- Header ---- */}
      <header className="bg-slate-900/95 border-b border-slate-700 dashboard-divider sticky top-0 z-30 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-14 lg:h-16">
            {/* Left: title */}
            <h1 className="text-lg lg:text-xl font-bold truncate dashboard-title">
              Test Squadron Admin
            </h1>

            {/* Right: actions */}
            {isMobile ? (
              /* Mobile: hamburger overflow menu */
              <div className="relative">
                <button
                  onClick={() => setMobileMenuOpen((v) => !v)}
                  className="min-h-[44px] min-w-[44px] flex items-center justify-center text-gray-300 hover:text-yellow-300"
                  aria-label="Menu"
                >
                  <span className="text-xl">{mobileMenuOpen ? '✕' : '☰'}</span>
                </button>

                {mobileMenuOpen && (
                  <div className="absolute right-0 top-full mt-1 w-56 bg-slate-900 border border-slate-700 dashboard-divider rounded-lg shadow-xl py-1 z-50">
                    <div className="px-4 py-2 border-b border-slate-700 dashboard-divider">
                      <p className="text-sm text-white truncate">{user.username}#{user.discriminator}</p>
                      <div className="mt-1">{roleBadge}</div>
                    </div>
                    <button
                      onClick={() => { handleSwitchServer(); setMobileMenuOpen(false); }}
                      className="w-full text-left px-4 py-3 text-sm text-yellow-300 hover:bg-slate-800 min-h-[44px]"
                    >
                      🔄 Switch Server
                    </button>
                    <button
                      onClick={() => { handleLogout(); setMobileMenuOpen(false); }}
                      className="w-full text-left px-4 py-3 text-sm text-red-400 hover:bg-slate-700 min-h-[44px]"
                    >
                      🚪 Logout
                    </button>
                  </div>
                )}
              </div>
            ) : (
              /* Desktop: inline controls */
              <div className="flex items-center space-x-4">
                <button
                  onClick={handleSwitchServer}
                  className="px-3 py-1 text-sm font-medium rounded transition border border-yellow-500/50 bg-yellow-500/10 text-yellow-300 hover:bg-yellow-500/20"
                >
                  🔄 Switch Server
                </button>
                <button
                  onClick={handleLogout}
                  className="px-3 py-1 text-sm font-medium bg-red-700 text-white rounded hover:bg-red-600 transition"
                >
                  🚪 Logout
                </button>
                <span className="text-sm text-gray-400">
                  {user.username}#{user.discriminator}
                </span>
                {roleBadge}
              </div>
            )}
          </div>
        </div>
      </header>

      {/* ---- Desktop tab strip (hidden on mobile) ---- */}
      <div className="hidden lg:block bg-slate-900/95 border-b border-slate-700 dashboard-divider">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <nav className="flex space-x-8" aria-label="Primary">
            {visibleNavItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) =>
                  cn(
                    'py-4 px-1 border-b-2 font-medium text-sm transition whitespace-nowrap',
                    isActive
                      ? 'dashboard-tab-active'
                      : 'border-transparent text-gray-400 hover:text-yellow-200',
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </div>

      {/* ---- Page content ---- */}
      <main className={cn(
        'flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-4 lg:py-8',
        isMobile && 'pb-20', // clear bottom nav on mobile
      )}>
        <Outlet />
      </main>

      {/* ---- Mobile bottom nav ---- */}
      {isMobile && <MobileNav items={navItems} />}
    </div>
  );
}
