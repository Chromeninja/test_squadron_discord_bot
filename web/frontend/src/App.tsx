import { Navigate, Route, Routes } from 'react-router-dom';
import { DashboardShell } from './components/layout/DashboardShell';
import { useAuth } from './contexts/AuthContext';
import Dashboard from './pages/Dashboard';
import Users from './pages/Users';
import Voice from './pages/Voice';
import Metrics from './pages/Metrics';
import SelectServer from './pages/SelectServer';
import DashboardBotSettings from './pages/DashboardBotSettings';
import Tickets from './pages/Tickets';
import { hasPermission as hasPermissionFn } from './utils/permissions';

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
      <div className="min-h-screen flex flex-col items-center justify-center px-4">
        <div className="bg-slate-800 p-8 rounded-lg shadow-xl text-center max-w-md w-full">
          <h1 className="text-2xl sm:text-3xl font-bold mb-4">Test Squadron Admin</h1>
          <p className="text-gray-400 mb-6">
            Admin dashboard for bot management
          </p>
          <a
            href="/auth/login"
            className="inline-block bg-indigo-600 hover:bg-indigo-700 text-white font-semibold px-6 py-3 rounded-lg transition min-h-[44px]"
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
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="bg-slate-800 p-8 rounded-lg shadow-xl text-center max-w-md w-full">
          <h1 className="text-2xl font-bold mb-4 text-red-400">Access Denied</h1>
          <p className="text-gray-400 mb-4">
            You do not have permission to access this dashboard.
          </p>
          <p className="text-sm text-gray-500">
            Contact a bot administrator if you believe this is an error.
          </p>
        </div>
      </div>
    );
  }

  // ---- No guild selected ----
  if (!user.active_guild_id) {
    return <SelectServer onSelected={refreshProfile} user={user} />;
  }

  // ---- Authenticated + guild selected → routed shell ----
  return (
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
  );
}

export default App;
