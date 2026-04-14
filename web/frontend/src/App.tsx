import { Suspense, lazy, useEffect, useState } from 'react';
import { Navigate, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom';
import { authApi, type UserProfile } from './api/endpoints';
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
const Landing = lazy(() => import('./pages/Landing'));

function PageFallback() {
  return (
    <div className="dashboard-theme flex min-h-screen items-center justify-center">
      <div className="text-xl text-[#f5deb3]">Loading...</div>
    </div>
  );
}

function buildDashboardPath(guildId: string, childPath: string = ''): string {
  const encodedGuildId = encodeURIComponent(guildId);
  const normalizedChild = childPath.replace(/^\/+/, '');
  return normalizedChild
    ? `/dashboard/${encodedGuildId}/${normalizedChild}`
    : `/dashboard/${encodedGuildId}`;
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

function LegacyGuildRouteRedirect({ childPath }: { childPath: string }) {
  const { user } = useAuth();

  if (!user?.active_guild_id || user.active_guild_id === '*') {
    return <Navigate to="/select-server" replace />;
  }

  return <Navigate to={buildDashboardPath(user.active_guild_id, childPath)} replace />;
}

function LegacyEventEditorRedirect() {
  const { eventId } = useParams();
  return <LegacyGuildRouteRedirect childPath={`events/${eventId ?? ''}/edit`} />;
}

function AuthenticatedLandingRoute({ user }: { user: UserProfile }) {
  const dashboardHref =
    user.active_guild_id && user.active_guild_id !== '*'
      ? buildDashboardPath(user.active_guild_id)
      : '/select-server';

  return <Landing loginHref="/auth/login?next=%2F" user={user} dashboardHref={dashboardHref} />;
}

function SelectServerRoute({
  user,
  onSelected,
}: {
  user: UserProfile;
  onSelected: () => Promise<void>;
}) {
  if (user.active_guild_id && user.active_guild_id !== '*') {
    return <Navigate to={buildDashboardPath(user.active_guild_id)} replace />;
  }

  return <SelectServer onSelected={onSelected} user={user} />;
}

function GuildScopeGate({
  user,
  onRefreshProfile,
  children,
}: {
  user: UserProfile;
  onRefreshProfile: () => Promise<void>;
  children: React.ReactNode;
}) {
  const { guildId } = useParams();
  const navigate = useNavigate();
  const [isSwitching, setIsSwitching] = useState(false);
  const [switchError, setSwitchError] = useState(false);

  const requestedGuildId = guildId ?? '';
  const isAuthorizedForRequestedGuild = Boolean(
    requestedGuildId && user.authorized_guilds?.[requestedGuildId],
  );

  useEffect(() => {
    if (!requestedGuildId) {
      setSwitchError(true);
      return;
    }

    if (!isAuthorizedForRequestedGuild) {
      setSwitchError(true);
      return;
    }

    if (user.active_guild_id === requestedGuildId) {
      setSwitchError(false);
      setIsSwitching(false);
      return;
    }

    let cancelled = false;

    const syncGuildContext = async () => {
      setIsSwitching(true);
      try {
        await authApi.selectGuild(requestedGuildId);
        await onRefreshProfile();
        if (!cancelled) {
          setSwitchError(false);
        }
      } catch {
        if (!cancelled) {
          setSwitchError(true);
        }
      } finally {
        if (!cancelled) {
          setIsSwitching(false);
        }
      }
    };

    void syncGuildContext();

    return () => {
      cancelled = true;
    };
  }, [
    isAuthorizedForRequestedGuild,
    onRefreshProfile,
    requestedGuildId,
    user.active_guild_id,
  ]);

  useEffect(() => {
    if (!switchError) {
      return;
    }

    navigate('/select-server', { replace: true });
  }, [navigate, switchError]);

  if (switchError || isSwitching || user.active_guild_id !== requestedGuildId) {
    return <PageFallback />;
  }

  return <>{children}</>;
}

// ---------------------------------------------------------------------------
// App root
// ---------------------------------------------------------------------------

function App() {
  const location = useLocation();
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
    const nextPath = `${location.pathname}${location.search}${location.hash}` || '/';
    const loginHref = `/auth/login?next=${encodeURIComponent(nextPath)}`;

    return (
      <Suspense fallback={<PageFallback />}>
        <Landing loginHref={loginHref} user={null} />
      </Suspense>
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

  // ---- Authenticated routing ----
  return (
    <Suspense fallback={<PageFallback />}>
      <Routes>
        <Route path="/" element={<AuthenticatedLandingRoute user={user} />} />
        <Route path="/home" element={<AuthenticatedLandingRoute user={user} />} />

        <Route
          path="/select-server"
          element={<SelectServerRoute user={user} onSelected={refreshProfile} />}
        />

        <Route
          path="/dashboard/:guildId"
          element={
            <GuildScopeGate user={user} onRefreshProfile={refreshProfile}>
              <DashboardShell
                user={user}
                onUserChange={setUser}
                onRefreshProfile={refreshProfile}
              />
            </GuildScopeGate>
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
          <Route path="*" element={<Navigate to="." replace />} />
        </Route>

        {/* Legacy flat routes kept for backwards compatibility */}
        <Route path="/metrics" element={<LegacyGuildRouteRedirect childPath="metrics" />} />
        <Route path="/users" element={<LegacyGuildRouteRedirect childPath="users" />} />
        <Route path="/voice" element={<LegacyGuildRouteRedirect childPath="voice" />} />
        <Route path="/events" element={<LegacyGuildRouteRedirect childPath="events" />} />
        <Route path="/events/new" element={<LegacyGuildRouteRedirect childPath="events/new" />} />
        <Route path="/events/:eventId/edit" element={<LegacyEventEditorRedirect />} />
        <Route
          path="/events/drafts"
          element={<LegacyGuildRouteRedirect childPath="events/drafts" />}
        />
        <Route
          path="/events/recurring"
          element={<LegacyGuildRouteRedirect childPath="events/recurring" />}
        />
        <Route path="/tickets" element={<LegacyGuildRouteRedirect childPath="tickets" />} />
        <Route path="/settings" element={<LegacyGuildRouteRedirect childPath="settings" />} />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}

export default App;
