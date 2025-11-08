import { useEffect, useState } from 'react';
import { statsApi, StatsOverview } from '../api/endpoints';

function Dashboard() {
  const [stats, setStats] = useState<StatsOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    statsApi
      .getOverview()
      .then((data) => {
        setStats(data.data);
        setLoading(false);
      })
      .catch((err) => {
        setError('Failed to load statistics');
        setLoading(false);
      });
  }, []);

  if (loading) {
    return <div className="text-center py-8">Loading statistics...</div>;
  }

  if (error) {
    return (
      <div className="bg-red-900/20 border border-red-800 rounded-lg p-4">
        <p className="text-red-400">{error}</p>
      </div>
    );
  }

  if (!stats) {
    return <div className="text-center py-8">No statistics available</div>;
  }

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Dashboard Overview</h2>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
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
    </div>
  );
}

export default Dashboard;
