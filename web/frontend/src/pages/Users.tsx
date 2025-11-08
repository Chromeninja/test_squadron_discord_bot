import { useState } from 'react';
import { usersApi, VerificationRecord } from '../api/endpoints';

function Users() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<VerificationRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async () => {
    setLoading(true);
    setError(null);

    try {
      const data = await usersApi.search(query, page, 20);
      setResults(data.items);
      setTotal(data.total);
    } catch (err) {
      setError('Failed to search users');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">User Search</h2>

      {/* Search Bar */}
      <div className="bg-slate-800 rounded-lg p-4 mb-6 border border-slate-700">
        <div className="flex gap-4">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="Search by user ID, RSI handle, or moniker..."
            className="flex-1 bg-slate-900 border border-slate-600 rounded px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500"
          />
          <button
            onClick={handleSearch}
            disabled={loading}
            className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-600 px-6 py-2 rounded font-medium transition"
          >
            {loading ? 'Searching...' : 'Search'}
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-900/20 border border-red-800 rounded-lg p-4 mb-6">
          <p className="text-red-400">{error}</p>
        </div>
      )}

      {/* Results */}
      {results.length > 0 && (
        <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-slate-900">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">
                    User ID
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">
                    RSI Handle
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">
                    Status
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">
                    Moniker
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">
                    Last Updated
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {results.map((record) => (
                  <tr key={record.user_id} className="hover:bg-slate-700/50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-mono">
                      {record.user_id}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      {record.rsi_handle}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      <span
                        className={`px-2 py-1 text-xs font-semibold rounded ${
                          record.membership_status === 'main'
                            ? 'bg-green-900 text-green-200'
                            : record.membership_status === 'affiliate'
                            ? 'bg-blue-900 text-blue-200'
                            : record.membership_status === 'non_member'
                            ? 'bg-yellow-900 text-yellow-200'
                            : 'bg-gray-900 text-gray-400'
                        }`}
                      >
                        {record.membership_status || 'unknown'}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-300">
                      {record.community_moniker || '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-400">
                      {new Date(record.last_updated * 1000).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination info */}
          <div className="px-6 py-4 bg-slate-900 text-sm text-gray-400">
            Showing {results.length} of {total} results
          </div>
        </div>
      )}

      {/* No results */}
      {!loading && results.length === 0 && total === 0 && query && (
        <div className="text-center py-8 text-gray-400">No results found</div>
      )}
    </div>
  );
}

export default Users;
