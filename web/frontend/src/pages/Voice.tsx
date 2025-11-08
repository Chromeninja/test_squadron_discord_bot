import { useState, useEffect } from 'react';
import { voiceApi, VoiceChannelRecord, ActiveVoiceChannel } from '../api/endpoints';

function Voice() {
  const [userId, setUserId] = useState('');
  const [results, setResults] = useState<VoiceChannelRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Active channels state
  const [activeChannels, setActiveChannels] = useState<ActiveVoiceChannel[]>([]);
  const [activeLoading, setActiveLoading] = useState(true);
  const [activeError, setActiveError] = useState<string | null>(null);
  const [expandedChannels, setExpandedChannels] = useState<Set<number>>(new Set());

  // Load active channels on mount
  useEffect(() => {
    loadActiveChannels();
  }, []);

  const loadActiveChannels = async () => {
    setActiveLoading(true);
    setActiveError(null);

    try {
      const data = await voiceApi.getActive();
      setActiveChannels(data.items);
    } catch (err) {
      setActiveError('Failed to load active channels');
    } finally {
      setActiveLoading(false);
    }
  };

  const toggleChannel = (channelId: number) => {
    const newExpanded = new Set(expandedChannels);
    if (newExpanded.has(channelId)) {
      newExpanded.delete(channelId);
    } else {
      newExpanded.add(channelId);
    }
    setExpandedChannels(newExpanded);
  };

  const handleSearch = async () => {
    const userIdNum = parseInt(userId, 10);
    if (isNaN(userIdNum)) {
      setError('Please enter a valid user ID');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const data = await voiceApi.search(userIdNum);
      setResults(data.items);
    } catch (err) {
      setError('Failed to search voice channels');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Voice Channels</h2>

      {/* Active Channels List */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xl font-semibold">Active Voice Channels</h3>
          <button
            onClick={loadActiveChannels}
            className="text-sm text-indigo-400 hover:text-indigo-300"
          >
            Refresh
          </button>
        </div>

        {activeLoading && (
          <div className="bg-slate-800 rounded-lg p-8 text-center border border-slate-700">
            <p className="text-gray-400">Loading active channels...</p>
          </div>
        )}

        {activeError && (
          <div className="bg-red-900/20 border border-red-800 rounded-lg p-4 mb-4">
            <p className="text-red-400">{activeError}</p>
          </div>
        )}

        {!activeLoading && !activeError && activeChannels.length === 0 && (
          <div className="bg-slate-800 rounded-lg p-8 text-center border border-slate-700">
            <p className="text-gray-400">No active voice channels</p>
          </div>
        )}

        {!activeLoading && activeChannels.length > 0 && (
          <div className="space-y-2">
            {activeChannels.map((channel) => (
              <div
                key={channel.voice_channel_id}
                className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden"
              >
                {/* Channel Header (Collapsible) */}
                <button
                  onClick={() => toggleChannel(channel.voice_channel_id)}
                  className="w-full px-6 py-4 flex items-center justify-between hover:bg-slate-700/50 transition"
                >
                  <div className="flex items-center gap-4">
                    <svg
                      className={`w-5 h-5 text-gray-400 transition-transform ${
                        expandedChannels.has(channel.voice_channel_id) ? 'rotate-90' : ''
                      }`}
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 5l7 7-7 7"
                      />
                    </svg>
                    <div className="text-left">
                      <p className="font-medium">
                        {channel.channel_name || `Channel ${channel.voice_channel_id}`}
                      </p>
                      <p className="text-sm text-gray-400">
                        Channel ID: {channel.voice_channel_id} • Owner: {channel.owner_rsi_handle || `User ${channel.owner_id}`}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className="text-sm text-gray-400">
                      {channel.members.length} {channel.members.length === 1 ? 'member' : 'members'}
                    </span>
                    <span className="text-sm text-gray-400">
                      {new Date(channel.last_activity * 1000).toLocaleString()}
                    </span>
                  </div>
                </button>

                {/* Channel Details (Expanded) */}
                {expandedChannels.has(channel.voice_channel_id) && (
                  <div className="px-6 py-4 bg-slate-900/50 border-t border-slate-700">
                    <h4 className="font-medium mb-3">Members:</h4>
                    
                    {channel.members.length === 0 ? (
                      <p className="text-sm text-gray-400 italic">
                        No members tracked (requires bot Gateway integration for real-time data)
                      </p>
                    ) : (
                      <div className="space-y-1">
                        {channel.members.map((member) => (
                          <div
                            key={member.user_id}
                            className="flex items-center gap-3 py-1.5 px-2 hover:bg-slate-800 rounded text-sm"
                          >
                            <span className="flex-1 font-medium">
                              {member.display_name || member.rsi_handle || member.username || `User ${member.user_id}`}
                            </span>
                            <span className="text-gray-500">→</span>
                            <span className="font-mono text-gray-400 text-xs">{member.user_id}</span>
                            <span className="text-gray-500">-</span>
                            {member.is_owner && (
                              <>
                                <span className="px-2 py-0.5 text-xs font-semibold rounded bg-indigo-900 text-indigo-200">
                                  Owner
                                </span>
                                <span className="text-gray-500">-</span>
                              </>
                            )}
                            {member.membership_status ? (
                              <span
                                className={`px-2 py-0.5 text-xs font-semibold rounded ${
                                  member.membership_status === 'main'
                                    ? 'bg-green-900 text-green-200'
                                    : member.membership_status === 'affiliate'
                                    ? 'bg-blue-900 text-blue-200'
                                    : member.membership_status === 'non_member'
                                    ? 'bg-gray-700 text-gray-300'
                                    : 'bg-gray-800 text-gray-400'
                                }`}
                              >
                                {member.membership_status === 'main'
                                  ? 'Main'
                                  : member.membership_status === 'affiliate'
                                  ? 'Affiliate'
                                  : member.membership_status === 'non_member'
                                  ? 'Not Member'
                                  : 'Unknown'}
                              </span>
                            ) : (
                              <span className="px-2 py-0.5 text-xs font-semibold rounded bg-gray-800 text-gray-500">
                                Not Verified
                              </span>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Search Section */}
      <div className="border-t border-slate-700 pt-8">
        <h3 className="text-xl font-semibold mb-4">Search Voice Channels by Owner</h3>

        {/* Search Bar */}
        <div className="bg-slate-800 rounded-lg p-4 mb-6 border border-slate-700">
          <div className="flex gap-4">
            <input
            type="text"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="Enter Discord user ID..."
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
                    Voice Channel ID
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">
                    Guild ID
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">
                    JTC Channel
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">
                    Status
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">
                    Last Activity
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {results.map((record) => (
                  <tr key={record.id} className="hover:bg-slate-700/50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-mono">
                      {record.voice_channel_id}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-mono">
                      {record.guild_id}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-mono">
                      {record.jtc_channel_id}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      <span
                        className={`px-2 py-1 text-xs font-semibold rounded ${
                          record.is_active
                            ? 'bg-green-900 text-green-200'
                            : 'bg-gray-900 text-gray-400'
                        }`}
                      >
                        {record.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-400">
                      {new Date(record.last_activity * 1000).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Results count */}
          <div className="px-6 py-4 bg-slate-900 text-sm text-gray-400">
            Found {results.length} voice channel(s)
          </div>
        </div>
      )}

      {/* No results */}
      {!loading && results.length === 0 && userId && (
        <div className="text-center py-8 text-gray-400">
          No voice channels found for this user
        </div>
      )}
      </div>
    </div>
  );
}

export default Voice;
