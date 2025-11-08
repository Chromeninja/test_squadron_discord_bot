import { useEffect, useState } from 'react';
import { authApi, UserProfile } from './api/endpoints';
import Dashboard from './pages/Dashboard';
import Users from './pages/Users';
import Voice from './pages/Voice';

type Tab = 'dashboard' | 'users' | 'voice';

function App() {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>('dashboard');

  useEffect(() => {
    authApi
      .getMe()
      .then((data) => {
        setUser(data.user);
        setLoading(false);
      })
      .catch(() => {
        setLoading(false);
      });
  }, []);

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

  if (!user.is_admin && !user.is_moderator) {
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

  return (
    <div className="min-h-screen bg-slate-900">
      {/* Header */}
      <header className="bg-slate-800 border-b border-slate-700">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center">
              <h1 className="text-xl font-bold">Test Squadron Admin</h1>
            </div>
            <div className="flex items-center space-x-4">
              <span className="text-sm text-gray-400">
                {user.username}#{user.discriminator}
              </span>
              {user.is_admin && (
                <span className="px-2 py-1 text-xs font-semibold bg-red-900 text-red-200 rounded">
                  ADMIN
                </span>
              )}
              {user.is_moderator && !user.is_admin && (
                <span className="px-2 py-1 text-xs font-semibold bg-blue-900 text-blue-200 rounded">
                  MOD
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
          </nav>
        </div>
      </div>

      {/* Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {activeTab === 'dashboard' && <Dashboard />}
        {activeTab === 'users' && <Users />}
        {activeTab === 'voice' && <Voice />}
      </main>
    </div>
  );
}

export default App;
