import { useCallback, useEffect, useState } from 'react';
import { Toaster } from 'react-hot-toast';
import { authApi, UserProfile } from './api/endpoints';
import Dashboard from './pages/Dashboard';
import Users from './pages/Users';
import Voice from './pages/Voice';
import SelectServer from './pages/SelectServer';
import DashboardBotSettings from './pages/DashboardBotSettings';
import { handleApiError } from './utils/toast';
import { hasPermission, getRoleBadgeColor, getRoleDisplayName, RoleLevel } from './utils/permissions';

type Tab = 'dashboard' | 'users' | 'voice' | 'bot-settings';

function App() {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>('dashboard');

  // Helper to get user's permission level in active guild
  const getUserRoleLevel = useCallback((): RoleLevel => {
    if (!user?.active_guild_id) return 'user';
    const permission = user.authorized_guilds[user.active_guild_id];
    return permission?.role_level || 'user';
  }, [user]);

  // Helper to check if user has minimum permission level
  const userHasPermission = useCallback((required: RoleLevel): boolean => {
    const userRole = getUserRoleLevel();
    return hasPermission(userRole, required);
  }, [getUserRoleLevel]);

  const fetchUserProfile = useCallback(() => {
    return authApi
      .getMe()
      .then((data) => {
        setUser(data.user);
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    fetchUserProfile();
  }, [fetchUserProfile]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-xl">Loading...</div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center">
        <div className="bg-slate-800 p-8 rounded-lg shadow-xl text-center max-w-md">
          <h1 className="text-3xl font-bold mb-4">Test Squadron Admin</h1>
          <p className="text-gray-400 mb-6">
            Admin dashboard for bot management
          </p>
          <a
            href="/auth/login"
            className="inline-block bg-indigo-600 hover:bg-indigo-700 text-white font-semibold px-6 py-3 rounded-lg transition"
          >
            Login with Discord
          </a>
        </div>
      </div>
    );
  }

  // Check if user has any permissions
  // Fallback: if authorized_guilds doesn't exist, fall back to is_admin/is_moderator
  const hasAnyPermissions = (() => {
    // Check for older session format
    if (user.is_admin || user.is_moderator) {
      return true;
    }
    
    // Check new format: user needs at least staff level in active guild
    if (user.active_guild_id && user.authorized_guilds) {
      const guildPerm = user.authorized_guilds[user.active_guild_id];
      return guildPerm && hasPermission(guildPerm.role_level, 'staff');
    }
    
    // Check if user has permissions in ANY guild (e.g., bot owner)
    if (user.authorized_guilds && Object.keys(user.authorized_guilds).length > 0) {
      return true;
    }
    
    return false;
  })();

  if (!hasAnyPermissions) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="bg-slate-800 p-8 rounded-lg shadow-xl text-center max-w-md">
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

  if (!user.active_guild_id) {
    return <SelectServer onSelected={fetchUserProfile} />;
  }

  const handleSwitchServer = async () => {
    try {
      await authApi.clearActiveGuild();
      // Refresh user profile to trigger SelectServer screen
      await fetchUserProfile();
    } catch (err) {
      handleApiError(err, 'Failed to switch server');
    }
  };

  const handleLogout = async () => {
    try {
      await authApi.logout();
      setUser(null);
      window.location.href = '/';
    } catch (err) {
      handleApiError(err, 'Failed to log out');
    }
  };

  return (
    <div className="min-h-screen bg-slate-900">
      {/* Toast notifications */}
      <Toaster />

      {/* Header */}
      <header className="bg-slate-800 border-b border-slate-700">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center">
              <h1 className="text-xl font-bold">Test Squadron Admin</h1>
            </div>
            <div className="flex items-center space-x-4">
              <button
                onClick={handleSwitchServer}
                className="px-3 py-1 text-sm font-medium bg-slate-700 text-gray-300 rounded hover:bg-slate-600 transition"
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
              {/* Show role badge - new format */}
              {user.active_guild_id && user.authorized_guilds?.[user.active_guild_id] && (
                <span className={`px-2 py-1 text-xs font-semibold rounded ${
                  getRoleBadgeColor(user.authorized_guilds[user.active_guild_id].role_level)
                }`}>
                  {getRoleDisplayName(user.authorized_guilds[user.active_guild_id].role_level).toUpperCase()}
                </span>
              )}
              {/* Fallback for sessions without authorized_guilds */}
              {(!user.authorized_guilds || !user.active_guild_id) && user.is_admin && (
                <span className="px-2 py-1 text-xs font-semibold bg-red-900 text-red-200 rounded">
                  ADMIN (FALLBACK)
                </span>
              )}
              {(!user.authorized_guilds || !user.active_guild_id) && user.is_moderator && !user.is_admin && (
                <span className="px-2 py-1 text-xs font-semibold bg-blue-900 text-blue-200 rounded">
                  MOD (FALLBACK)
                </span>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Tabs */}
      <div className="bg-slate-800 border-b border-slate-700">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <nav className="flex space-x-8">
            <button
              onClick={() => setActiveTab('dashboard')}
              className={`py-4 px-1 border-b-2 font-medium text-sm transition ${
                activeTab === 'dashboard'
                  ? 'border-indigo-500 text-indigo-500'
                  : 'border-transparent text-gray-400 hover:text-gray-300'
              }`}
            >
              Dashboard
            </button>
            <button
              onClick={() => setActiveTab('users')}
              className={`py-4 px-1 border-b-2 font-medium text-sm transition ${
                activeTab === 'users'
                  ? 'border-indigo-500 text-indigo-500'
                  : 'border-transparent text-gray-400 hover:text-gray-300'
              }`}
            >
              Users
            </button>
            <button
              onClick={() => setActiveTab('voice')}
              className={`py-4 px-1 border-b-2 font-medium text-sm transition ${
                activeTab === 'voice'
                  ? 'border-indigo-500 text-indigo-500'
                  : 'border-transparent text-gray-400 hover:text-gray-300'
              }`}
            >
              Voice
            </button>
            {userHasPermission('bot_admin') && (
              <button
                onClick={() => setActiveTab('bot-settings')}
                className={`py-4 px-1 border-b-2 font-medium text-sm transition ${
                  activeTab === 'bot-settings'
                    ? 'border-indigo-500 text-indigo-500'
                    : 'border-transparent text-gray-400 hover:text-gray-300'
                }`}
              >
                Bot Settings
              </button>
            )}
          </nav>
        </div>
      </div>

      {/* Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {activeTab === 'dashboard' && <Dashboard />}
        {activeTab === 'users' && <Users />}
        {activeTab === 'voice' && <Voice />}
        {activeTab === 'bot-settings' && userHasPermission('bot_admin') && user.active_guild_id && (
          <DashboardBotSettings guildId={user.active_guild_id} />
        )}
      </main>
    </div>
  );
}

export default App;
