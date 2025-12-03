import { useEffect, useState } from 'react';
import { 
  statsApi, 
  StatsOverview, 
  healthApi, 
  HealthOverview, 
  errorsApi, 
  StructuredError,
  logsApi,
  authApi
} from '../api/endpoints';

function Dashboard() {
  const [stats, setStats] = useState<StatsOverview | null>(null);
  const [health, setHealth] = useState<HealthOverview | null>(null);
  const [lastError, setLastError] = useState<StructuredError | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = async () => {
    try {
      setRefreshing(true);
      
      // Fetch user profile to check admin status
      const userResponse = await authApi.getMe();
      const userIsAdmin = userResponse.user?.is_admin || false;
      setIsAdmin(userIsAdmin);
      
      // Fetch stats (available to all authenticated users)
      const statsResponse = await statsApi.getOverview();
      setStats(statsResponse.data);
      
      // Fetch admin-only data
      if (userIsAdmin) {
        try {
          const healthResponse = await healthApi.getOverview();
          setHealth(healthResponse.data);
        } catch (err) {
          console.error('Failed to fetch health data:', err);
        }
        
        try {
          const errorsResponse = await errorsApi.getLast(1);
          setLastError(errorsResponse.errors[0] || null);
        } catch (err) {
          console.error('Failed to fetch error data:', err);
        }
      }
      
      setLoading(false);
      setError(null);
    } catch (err) {
      setError('Failed to load dashboard data');
      setLoading(false);
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleRefresh = () => {
    fetchData();
  };

  const handleExportLogs = async () => {
    try {
      await logsApi.exportLogs();
    } catch (err) {
      console.error('Failed to export logs:', err);
      alert('Failed to export logs. Please try again.');
    }
  };

  const handleExportBackendLogs = async () => {
    try {
      await logsApi.exportBackendLogs();
    } catch (err) {
      console.error('Failed to export backend logs:', err);
      alert('Failed to export backend logs. Please try again.');
    }
  };

  const handleExportAuditLogs = async () => {
    try {
      await logsApi.exportAuditLogs();
    } catch (err) {
      console.error('Failed to export audit logs:', err);
      alert('Failed to export audit logs. Please try again.');
    }
  };

  const formatUptime = (seconds: number): string => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    
    if (hours > 0) {
      return `${hours}h ${minutes}m ${secs}s`;
    } else if (minutes > 0) {
      return `${minutes}m ${secs}s`;
    } else {
      return `${secs}s`;
    }
  };

  const getStatusBadge = (status: string): string => {
    switch (status) {
      case 'healthy':
        return 'bg-green-500/20 text-green-400 border-green-500/50';
      case 'degraded':
        return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50';
      case 'unhealthy':
        return 'bg-red-500/20 text-red-400 border-red-500/50';
      default:
        return 'bg-gray-500/20 text-gray-400 border-gray-500/50';
    }
  };

  if (loading) {
    return <div className="text-center py-8">Loading dashboard...</div>;
  }

  if (error) {
    return (
      <div className="bg-red-900/20 border border-red-800 rounded-lg p-4">
        <p className="text-red-400">{error}</p>
        <button
          onClick={handleRefresh}
          className="mt-4 px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-md transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!stats) {
    return <div className="text-center py-8">No data available</div>;
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold">Dashboard Overview</h2>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 rounded-md transition-colors flex items-center gap-2"
        >
          <svg
            className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
          {refreshing ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {/* Main Stats - Visible to all authenticated users */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-6">
        {/* Total Verified */}
        <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
          <h3 className="text-sm font-medium text-gray-400 mb-2">
            Total Verified
          </h3>
          <p className="text-3xl font-bold">{stats.total_verified}</p>
        </div>

        {/* Voice Active */}
        <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
          <h3 className="text-sm font-medium text-gray-400 mb-2">
            Active Voice Channels
          </h3>
          <p className="text-3xl font-bold">{stats.voice_active_count}</p>
        </div>

        {/* Status Breakdown */}
        <div className="bg-slate-800 rounded-lg p-6 border border-slate-700 md:col-span-2 lg:col-span-1">
          <h3 className="text-sm font-medium text-gray-400 mb-4">
            Membership Status
          </h3>
          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-green-400">Main</span>
              <span className="font-semibold">{stats.by_status.main}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-blue-400">Affiliate</span>
              <span className="font-semibold">{stats.by_status.affiliate}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-yellow-400">Non-Member</span>
              <span className="font-semibold">{stats.by_status.non_member}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Unknown</span>
              <span className="font-semibold">{stats.by_status.unknown}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Admin Section - Only visible to admins */}
      {isAdmin && (
        <>
          <h3 className="text-xl font-bold mt-8 mb-4">Admin Monitoring</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {/* Bot Health Card */}
            {health && (
              <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
                <h3 className="text-sm font-medium text-gray-400 mb-3">
                  Bot Health
                </h3>
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm">Status:</span>
                    <span
                      className={`px-3 py-1 rounded-full text-xs font-semibold border ${getStatusBadge(
                        health.status
                      )}`}
                    >
                      {health.status.toUpperCase()}
                    </span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-400">Uptime:</span>
                    <span className="font-semibold">
                      {formatUptime(health.uptime_seconds)}
                    </span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-400">Database:</span>
                    <span
                      className={`font-semibold ${
                        health.db_ok ? 'text-green-400' : 'text-red-400'
                      }`}
                    >
                      {health.db_ok ? 'OK' : 'ERROR'}
                    </span>
                  </div>
                  {health.discord_latency_ms !== null && (
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-400">Gateway Latency:</span>
                      <span className="font-semibold">
                        {health.discord_latency_ms.toFixed(1)}ms
                      </span>
                    </div>
                  )}
                  <div className="pt-2 border-t border-slate-700">
                    <details className="cursor-pointer">
                      <summary className="text-sm text-gray-400 hover:text-gray-300">
                        System Resources
                      </summary>
                      <div className="mt-2 space-y-2">
                        <div className="flex justify-between text-sm">
                          <span className="text-gray-400">CPU:</span>
                          <span className="font-semibold">
                            {health.system.cpu_percent.toFixed(1)}%
                          </span>
                        </div>
                        <div className="flex justify-between text-sm">
                          <span className="text-gray-400">Memory:</span>
                          <span className="font-semibold">
                            {health.system.memory_percent.toFixed(1)}%
                          </span>
                        </div>
                      </div>
                    </details>
                  </div>
                </div>
              </div>
            )}

            {/* Last Error Card */}
            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
              <h3 className="text-sm font-medium text-gray-400 mb-3">
                Last Error
              </h3>
              {lastError ? (
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-400">Type:</span>
                    <span className="font-semibold text-red-400">
                      {lastError.error_type}
                    </span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-400">Component:</span>
                    <span className="font-semibold">
                      {lastError.component}
                    </span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-400">Time:</span>
                    <span className="font-semibold text-xs">
                      {new Date(lastError.time).toLocaleString()}
                    </span>
                  </div>
                  {lastError.message && (
                    <div className="mt-2 pt-2 border-t border-slate-700">
                      <p className="text-xs text-gray-400 line-clamp-3">
                        {lastError.message}
                      </p>
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-center py-4">
                  <p className="text-green-400 text-sm">No recent errors</p>
                </div>
              )}
            </div>

            {/* Admin Actions Card */}
            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
              <h3 className="text-sm font-medium text-gray-400 mb-3">
                Actions
              </h3>
              <div className="space-y-3">
                <button
                  onClick={handleExportLogs}
                  className="w-full px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-md transition-colors text-sm flex items-center justify-center gap-2"
                >
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                    />
                  </svg>
                  Export Bot Logs
                </button>
                <button
                  onClick={handleExportBackendLogs}
                  className="w-full px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-md transition-colors text-sm flex items-center justify-center gap-2"
                >
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                    />
                  </svg>
                  Export Backend Logs
                </button>
                <button
                  onClick={handleExportAuditLogs}
                  className="w-full px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-md transition-colors text-sm flex items-center justify-center gap-2"
                >
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                    />
                  </svg>
                  Export Audit Logs
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default Dashboard;
