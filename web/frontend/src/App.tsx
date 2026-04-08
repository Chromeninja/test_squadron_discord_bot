import { Suspense, lazy } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { DashboardShell } from './components/layout/DashboardShell';
import { useAuth } from './contexts/AuthContext';
import { hasPermission as hasPermissionFn } from './utils/permissions';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const Users = lazy(() => import('./pages/Users'));
const Voice = lazy(() => import('./pages/Voice'));
const Metrics = lazy(() => import('./pages/Metrics'));
const SelectServer = lazy(() => import('./pages/SelectServer'));
const DashboardBotSettings = lazy(() => import('./pages/DashboardBotSettings'));
const Tickets = lazy(() => import('./pages/Tickets'));
const Events = lazy(() => import('./pages/Events'));
const EventEditor = lazy(() => import('./pages/EventEditor'));
const EventDrafts = lazy(() => import('./pages/EventDrafts'));
const EventRecurring = lazy(() => import('./pages/EventRecurring'));

function PageFallback() {
  return (
    <div className="dashboard-theme flex min-h-screen items-center justify-center">
      <div className="text-xl text-[#f5deb3]">Loading...</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Route guards
// ---------------------------------------------------------------------------

/**
 * Wrapper that only renders children when the user meets a minimum role.
 * Otherwise redirects to the dashboard.
 */
function RequireRole({
  minRole,
  children,
}: {
  minRole: Parameters<ReturnType<typeof useAuth>['userHasPermission']>[0];
  children: React.ReactNode;
}) {
  const { userHasPermission } = useAuth();
  if (!userHasPermission(minRole)) return <Navigate to="/" replace />;
  return <>{children}</>;
}

/**
 * Wrapper that renders children only when an active guild is selected.
 */
function RequireGuild({ children }: { children: (guildId: string) => React.ReactNode }) {
  const { activeGuildId } = useAuth();
  if (!activeGuildId || activeGuildId === '*') return <Navigate to="/" replace />;
  return <>{children(activeGuildId)}</>;
}

// ---------------------------------------------------------------------------
// App root
// ---------------------------------------------------------------------------

function App() {
  const { user, loading, setUser, refreshProfile } = useAuth();

  // ---- Loading state ----
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-xl">Loading...</div>
      </div>
    );
  }

  // ---- Not authenticated ----
  if (!user) {
    return (
      <div className="dashboard-theme flex min-h-screen flex-col items-center justify-center px-4">
        <div className="w-full max-w-md rounded-2xl border border-[#ffbb00]/18 bg-[linear-gradient(180deg,rgba(20,23,31,0.96),rgba(8,9,12,0.98))] p-8 text-center shadow-[0_0_30px_rgba(255,187,0,0.08)]">
          <h1 className="mb-4 text-2xl font-bold text-[#fff4cc] sm:text-3xl">TEST Squadron Command</h1>
          <p className="mb-6 text-[#a89465]">
            Admin dashboard for bot management
          </p>
          <a
            href="/auth/login"
            className="inline-block min-h-[44px] rounded-lg border border-[#ffbb00]/45 bg-[linear-gradient(180deg,rgba(255,187,0,0.22),rgba(255,187,0,0.12))] px-6 py-3 font-semibold text-[#fff1bf] transition hover:bg-[linear-gradient(180deg,rgba(255,187,0,0.3),rgba(255,187,0,0.16))]"
          >
            Login with Discord
          </a>
        </div>
      </div>
    );
  }

  // ---- Permission check ----
  const hasAnyPermissions = (() => {
    if (user.is_bot_owner) return true;
    if (user.is_admin || user.is_moderator) return true;
    if (
      user.active_guild_id &&
      user.active_guild_id !== '*' &&
      user.authorized_guilds
    ) {
      const guildPerm = user.authorized_guilds[user.active_guild_id];
      return guildPerm && hasPermissionFn(guildPerm.role_level, 'staff');
    }
    if (user.authorized_guilds && Object.keys(user.authorized_guilds).length > 0)
      return true;
    return false;
  })();

  if (!hasAnyPermissions) {
    return (
      <div className="dashboard-theme flex min-h-screen items-center justify-center px-4">
        <div className="w-full max-w-md rounded-2xl border border-[#ffbb00]/18 bg-[linear-gradient(180deg,rgba(20,23,31,0.96),rgba(8,9,12,0.98))] p-8 text-center shadow-[0_0_30px_rgba(255,187,0,0.08)]">
          <h1 className="mb-4 text-2xl font-bold text-[#ffdd73]">Access Denied</h1>
          <p className="mb-4 text-[#d6c7a3]">
            You do not have permission to access this dashboard.
          </p>
          <p className="text-sm text-[#a89465]">
            Contact a bot administrator if you believe this is an error.
          </p>
        </div>
      </div>
    );
  }

  // ---- No guild selected ----
  if (!user.active_guild_id) {
    return (
      <Suspense fallback={<PageFallback />}>
        <SelectServer onSelected={refreshProfile} user={user} />
      </Suspense>
    );
  }

  // ---- Authenticated + guild selected → routed shell ----
  return (
    <Suspense fallback={<PageFallback />}>
      <Routes>
        <Route
          element={
            <DashboardShell
              user={user}
              onUserChange={setUser}
              onRefreshProfile={refreshProfile}
            />
          }
        >
          {/* Dashboard (index route) */}
          <Route index element={<Dashboard />} />

          {/* Metrics — discord_manager+ */}
          <Route
            path="metrics"
            element={
              <RequireRole minRole="discord_manager">
                <Metrics />
              </RequireRole>
            }
          />

          {/* Users */}
          <Route path="users" element={<Users />} />

          {/* Voice */}
          <Route path="voice" element={<Voice />} />

          {/* Events - event_coordinator+ and needs guildId */}
          <Route
            path="events"
            element={
              <RequireRole minRole="event_coordinator">
                <RequireGuild>
                  {(guildId) => <Events guildId={guildId} />}
                </RequireGuild>
              </RequireRole>
            }
          />

          <Route
            path="events/new"
            element={
              <RequireRole minRole="event_coordinator">
                <RequireGuild>
                  {(guildId) => <EventEditor guildId={guildId} mode="create" />}
                </RequireGuild>
              </RequireRole>
            }
          />

          <Route
            path="events/:eventId/edit"
            element={
              <RequireRole minRole="event_coordinator">
                <RequireGuild>
                  {(guildId) => <EventEditor guildId={guildId} mode="edit" />}
                </RequireGuild>
              </RequireRole>
            }
          />

          <Route
            path="events/drafts"
            element={
              <RequireRole minRole="event_coordinator">
                <RequireGuild>
                  {(guildId) => <EventDrafts guildId={guildId} />}
                </RequireGuild>
              </RequireRole>
            }
          />

          <Route
            path="events/recurring"
            element={
              <RequireRole minRole="event_coordinator">
                <RequireGuild>
                  {(guildId) => <EventRecurring guildId={guildId} />}
                </RequireGuild>
              </RequireRole>
            }
          />

          {/* Tickets — discord_manager+ and needs guildId */}
          <Route
            path="tickets"
            element={
              <RequireRole minRole="discord_manager">
                <RequireGuild>
                  {(guildId) => <Tickets guildId={guildId} />}
                </RequireGuild>
              </RequireRole>
            }
          />

          {/* Bot Settings — bot_admin+ and needs guildId */}
          <Route
            path="settings"
            element={
              <RequireRole minRole="bot_admin">
                <RequireGuild>
                  {(guildId) => <DashboardBotSettings guildId={guildId} />}
                </RequireGuild>
              </RequireRole>
            }
          />

          {/* Catch-all → redirect to dashboard */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </Suspense>
  );
}

export default App;
