import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  statsApi,
  StatsOverview,
  healthApi,
  HealthOverview,
  errorsApi,
  StructuredError,
  logsApi,
} from '../api/endpoints';
import { useAuth } from '../contexts/AuthContext';
import { handleApiError, showSuccess } from '../utils/toast';
import { hasPermission, RoleLevel } from '../utils/permissions';
import { Button, Card, Alert } from '../components/ui';

function Dashboard() {
  const { user } = useAuth();
  const [stats, setStats] = useState<StatsOverview | null>(null);
  const [health, setHealth] = useState<HealthOverview | null>(null);
  const [lastError, setLastError] = useState<StructuredError | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const requestSequenceRef = useRef(0);

  const isBotAdmin = useMemo(() => {
    if (!user) {
      return false;
    }
    if (user.is_admin || user.is_bot_owner) {
      return true;
    }
    if (user.active_guild_id && user.authorized_guilds?.[user.active_guild_id]) {
      const roleLevel = user.authorized_guilds[user.active_guild_id].role_level as RoleLevel;
      return hasPermission(roleLevel, 'bot_admin');
    }
    return Object.values(user.authorized_guilds ?? {}).some((guildPerm) =>
      hasPermission(guildPerm.role_level as RoleLevel, 'bot_admin')
    );
  }, [user]);

  const fetchData = useCallback(async () => {
    const requestId = requestSequenceRef.current + 1;
    requestSequenceRef.current = requestId;

    try {
      setRefreshing(true);

      const [statsResponse, adminResults] = await Promise.all([
        statsApi.getOverview(),
        isBotAdmin
          ? Promise.allSettled([healthApi.getOverview(), errorsApi.getLast(1)])
          : Promise.resolve([] as PromiseSettledResult<unknown>[]),
      ]);

      if (requestId !== requestSequenceRef.current) {
        return;
      }

      setStats(statsResponse.data);

      if (isBotAdmin) {
        const [healthResult, errorsResult] = adminResults as [
          PromiseSettledResult<{ data: HealthOverview }>,
          PromiseSettledResult<{ errors: StructuredError[] }>,
        ];
        setHealth(
          healthResult?.status === 'fulfilled' ? healthResult.value.data : null,
        );
        setLastError(
          errorsResult?.status === 'fulfilled'
            ? errorsResult.value.errors[0] || null
            : null,
        );
      } else {
        setHealth(null);
        setLastError(null);
      }

      setError(null);
    } catch (err) {
      if (requestId !== requestSequenceRef.current) {
        return;
      }
      setError('Failed to load dashboard data');
    } finally {
      if (requestId === requestSequenceRef.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [isBotAdmin]);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  const handleRefresh = () => {
    void fetchData();
  };

  const exportActions: { label: string; action: () => Promise<void>; errorMsg: string }[] = [
    { label: 'Export Bot Logs', action: () => logsApi.exportLogs(), errorMsg: 'Failed to export bot logs' },
    { label: 'Export Backend Logs', action: () => logsApi.exportBackendLogs(), errorMsg: 'Failed to export backend logs' },
    { label: 'Export Audit Logs', action: () => logsApi.exportAuditLogs(), errorMsg: 'Failed to export audit logs' },
  ];

  const handleExport = async (action: () => Promise<void>, successMsg: string, errorMsg: string) => {
    try {
      await action();
      showSuccess(successMsg);
    } catch (err) {
      handleApiError(err, errorMsg);
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
      <Alert variant="error">
        <p>{error}</p>
        <Button variant="secondary" onClick={handleRefresh} className="mt-4">
          Retry
        </Button>
      </Alert>
    );
  }

  if (!stats) {
    return <div className="text-center py-8">No data available</div>;
  }

  return (
    <div className="space-y-6 lg:space-y-8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-2xl font-bold leading-tight dashboard-section-title">Dashboard Overview</h2>
        <Button
          onClick={handleRefresh}
          loading={refreshing}
          variant="secondary"
          size="sm"
          className="self-start sm:self-auto min-h-[40px] px-3 dashboard-accent-button"
          leftIcon={
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          }
        >
          {refreshing ? 'Refreshing...' : 'Refresh'}
        </Button>
      </div>

      {/* Main Stats - Visible to all authenticated users */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-2 sm:gap-3 lg:gap-6">
        {/* Total Verified */}
        <Card padding="none" className="p-3 sm:p-4 lg:p-6 dashboard-panel">
          <h3 className="text-sm font-medium text-gray-400 mb-1.5">
            Total Verified
          </h3>
          <p className="text-xl sm:text-2xl lg:text-3xl font-bold leading-tight text-yellow-200">{stats.total_verified}</p>
        </Card>

        {/* Voice Active */}
        <Card padding="none" className="p-3 sm:p-4 lg:p-6 dashboard-panel">
          <h3 className="text-sm font-medium text-gray-400 mb-1.5">
            Active Voice Channels
          </h3>
          <p className="text-xl sm:text-2xl lg:text-3xl font-bold leading-tight text-yellow-200">{stats.voice_active_count}</p>
        </Card>

        {/* Status Breakdown */}
        <Card padding="none" className="col-span-2 lg:col-span-1 p-3 sm:p-4 lg:p-6 dashboard-panel">
          <h3 className="text-sm font-medium text-gray-400 mb-3">
            Membership Status
          </h3>
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-green-400">Main</span>
              <span className="font-semibold">{stats.by_status.main}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-blue-400">Affiliate</span>
              <span className="font-semibold">{stats.by_status.affiliate}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-yellow-400">Non-Member</span>
              <span className="font-semibold">{stats.by_status.non_member}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-400">Unknown</span>
              <span className="font-semibold">{stats.by_status.unknown}</span>
            </div>
          </div>
        </Card>
      </div>

      {/* Admin Section - Only visible to bot admins and bot owners */}
      {isBotAdmin && (
        <>
          <h3 className="text-xl font-bold dashboard-section-title">Admin Monitoring</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 lg:gap-6">
            {/* Bot Health Card */}
            {health && (
              <Card padding="none" className="p-4 sm:p-5 lg:p-6 dashboard-panel">
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
              </Card>
            )}

            {/* Last Error Card */}
            <Card padding="none" className="p-4 sm:p-5 lg:p-6 dashboard-panel">
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
            </Card>

            {/* Admin Actions Card */}
            <Card padding="none" className="p-4 sm:p-5 lg:p-6 dashboard-panel">
              <h3 className="text-sm font-medium text-gray-400 mb-3">
                Actions
              </h3>
              <div className="space-y-2">
                {exportActions.map(({ label, action, errorMsg }) => (
                  <Button
                    key={label}
                    variant="secondary"
                    size="sm"
                    fullWidth
                    className="min-h-[40px] justify-start border-yellow-500/40 text-yellow-200 hover:bg-yellow-500/15"
                    onClick={() => handleExport(action, `${label.replace('Export ', '')} exported successfully`, errorMsg)}
                    leftIcon={
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                      </svg>
                    }
                  >
                    {label}
                  </Button>
                ))}
              </div>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

export default Dashboard;
